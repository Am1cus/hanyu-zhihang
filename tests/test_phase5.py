import copy
import heapq
import json
import math
import random
import unittest

from Phase5.energy import integrate_discharge
from Phase5.planning import plan, mission_budget
from Phase5.risk import evaluate
from Phase5.telemetry_contract import decode, SAMPLING


class PlanningTests(unittest.TestCase):
    def grid(self):
        return dict(width=5, height=3, cell_size_m=10, start=[0,1], goal=[4,1],
                    blocked=[], energy_wh_per_m=[[1]*5, [1,10,10,10,1], [1]*5],
                    cost_source="synthetic_software_fixture")

    def test_distance_and_energy_choose_different_paths(self):
        s = self.grid()
        shortest, energy = plan(s), plan(s, "energy")
        self.assertEqual(shortest["distance_m"], 40)
        self.assertEqual(energy["distance_m"], 60)
        self.assertEqual(energy["estimated_energy_wh"], 60)
        self.assertEqual(shortest["estimated_energy_wh"], 310)

    def test_unreachable_and_blocked_endpoints(self):
        s = self.grid()
        s["blocked"] = [[2,y] for y in range(3)]
        self.assertEqual(plan(s)["status"], "unreachable")
        s["blocked"] = [s["start"]]
        self.assertEqual(plan(s)["reason"], "blocked_endpoint")

    def test_same_point_and_missing_cost(self):
        s = self.grid(); s["goal"] = s["start"]
        self.assertEqual(plan(s)["distance_m"], 0)
        del s["energy_wh_per_m"]
        self.assertIsNone(plan(s)["estimated_energy_wh"])
        self.assertEqual(plan(s,"energy")["status"], "unavailable")

    def test_invalid_inputs(self):
        for field,value in [("cell_size_m",0), ("width",True), ("goal",[5,0]), ("energy_wh_per_m",[[1]])]:
            s=self.grid();s[field]=value
            with self.assertRaises(ValueError): plan(s)
        for bad in (0,-1,float("nan"),True):
            s=self.grid();s["energy_wh_per_m"][0][0]=bad
            with self.assertRaises(ValueError): plan(s,"energy")

    def test_obstacle_update_replans_without_mutating_original(self):
        s=self.grid(); old=copy.deepcopy(s)
        first=plan(s,"energy")
        changed={**s,"blocked":[first["path"][2]]}
        replanned=plan(changed,"energy")
        self.assertEqual(s,old)
        self.assertNotIn(changed["blocked"][0],replanned["path"])

    def test_budget_requires_return_and_explicit_usable_wh(self):
        route=plan(self.grid(),"energy")
        self.assertEqual(mission_budget(route,route,130,10)["margin_wh"],0)
        self.assertEqual(mission_budget(route,route,129,10)["status"],"budget_exceeded")
        self.assertEqual(mission_budget(route,{},500,10)["status"],"unavailable")
        self.assertEqual(mission_budget(route,route,None,10)["status"],"unavailable")

    def test_astar_matches_independent_dijkstra_on_40_grids(self):
        rng=random.Random(20260913)
        for _ in range(40):
            costs=[[rng.uniform(.1,5) for x in range(6)] for y in range(6)]
            blocked={(x,y) for x in range(6) for y in range(6) if rng.random()<.2}-{(0,0),(5,5)}
            s=dict(width=6,height=6,cell_size_m=2,start=[0,0],goal=[5,5],blocked=list(blocked),energy_wh_per_m=costs)
            frontier=[(0,(0,0))]; done=set(); answer=math.inf
            while frontier:
                score,p=heapq.heappop(frontier)
                if p in done: continue
                done.add(p)
                if p==(5,5): answer=score;break
                for q in ((p[0]+1,p[1]),(p[0]-1,p[1]),(p[0],p[1]+1),(p[0],p[1]-1)):
                    if 0<=q[0]<6 and 0<=q[1]<6 and q not in blocked and q not in done:
                        heapq.heappush(frontier,(score+2*costs[q[1]][q[0]],q))
            actual=plan(s,"energy")
            if math.isinf(answer): self.assertEqual(actual["status"],"unreachable")
            else: self.assertAlmostEqual(actual["cost"],answer)


class RiskTests(unittest.TestCase):
    def rows(self, volts, alarms=(), run="a"):
        return [dict(run_id=run,t_s=i,voltage_v=v,risk=i in alarms) for i,v in enumerate(volts)]

    def test_lead_time_miss_and_false_positive(self):
        hit=self.rows([12,12,12,12,10,10,12,12,12],(2,6))
        result=evaluate(hit,11,2)
        self.assertEqual(result["events"][0]["lead_s"],2)
        self.assertEqual(result["counts"]["tp"],1)
        self.assertEqual(result["counts"]["fn"],1)
        self.assertEqual(result["counts"]["fp"],1)
        self.assertEqual(result["event_recall"],1)
        missed=evaluate(self.rows([12,12,12,10,10]),11,2)
        self.assertEqual(missed["missed_events"],1)

    def test_active_threshold_is_not_advance_warning(self):
        result=evaluate(self.rows([12,12,12,10,10],(3,4)),11,2)
        self.assertEqual(result["event_recall"],0)
        self.assertIsNone(result["events"][0]["lead_s"])
        recross=evaluate(self.rows([12,12,12,12,10,12,10],(2,)),11,4)
        self.assertEqual(recross["counts"]["eligible_events"],2)
        self.assertEqual(recross["counts"]["detected_events"],1)

    def test_no_event_and_tail_are_not_false_certainty(self):
        result=evaluate(self.rows([12]*5,(4,)),11,2)
        self.assertIsNone(result["event_recall"])
        self.assertEqual(result["counts"]["unlabelled"],2)
        self.assertEqual(result["counts"]["fp"],0)

    def test_gap_and_missing_voltage_do_not_bridge_labels(self):
        rows=self.rows([12,12,None,10,10])
        result=evaluate(rows,11,2)
        self.assertEqual(result["counts"]["eligible_events"],0)
        self.assertEqual(result["counts"]["tp"]+result["counts"]["fn"],0)
        rows=self.rows([12,12,10,10]);rows[2]["t_s"]=5;rows[3]["t_s"]=6
        self.assertEqual(evaluate(rows,11,2)["counts"]["eligible_events"],0)

    def test_unavailable_risk_is_abstention_and_event_miss(self):
        rows=self.rows([12,12,12,10,10])
        for row in rows: row["risk"]=None
        result=evaluate(rows,11,2)
        self.assertEqual(result["prediction_coverage"],0)
        self.assertEqual(result["missed_events"],1)
        self.assertIsNone(result["sample_recall_available"])

    def test_run_isolation_and_duplicate_rejection(self):
        rows=self.rows([12,12],run="a")+self.rows([10,10],run="b")
        self.assertEqual(evaluate(rows,11,2)["counts"]["eligible_events"],0)
        with self.assertRaises(ValueError): evaluate(rows+rows[:1],11,2)
        with self.assertRaises(ValueError): evaluate(rows,11,2.5)
        rows[0]["risk"]=1
        with self.assertRaises(ValueError): evaluate(rows,11,2)


class EnergyTests(unittest.TestCase):
    def test_units_and_no_remaining_energy_inference(self):
        rows=[dict(run_id="a",t_s=t,voltage_v=12,current_a=2) for t in (0,1800,3600)]
        result=integrate_discharge(rows,1800)
        self.assertEqual(result["discharged_wh"],24)
        self.assertEqual(result["discharged_ah"],2)
        self.assertIsNone(result["remaining_usable_wh"])

    def test_missing_gap_charging_and_cross_run(self):
        rows=[dict(run_id="a",t_s=t,voltage_v=12,current_a=2) for t in (0,2)]
        self.assertEqual(integrate_discharge(rows,1)["status"],"unavailable")
        rows[1]["current_a"]=None
        self.assertEqual(integrate_discharge(rows,2)["status"],"unavailable")
        rows[1]["current_a"]=-1
        self.assertEqual(integrate_discharge(rows,2)["reason"],"invalid_voltage_or_charging")
        rows[1]["run_id"]="b"
        with self.assertRaises(ValueError): integrate_discharge(rows,2)


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.run=dict(runId="run-a",flightId="F001",droneId=1,droneCode="sim-a",status="RUNNING",sampling_contract=SAMPLING)
        self.row={k:self.run[k] for k in ("runId","flightId","droneId","droneCode")}
        self.row.update(sampleSeq=0,sourceTimeS=1,windX=None)
        self.topic="cold-aviation/v1/sim-a/runs/run-a/telemetry"

    def payload(self):
        return json.dumps(dict(schema_version=1,sampling_contract=SAMPLING,telemetry=self.row))

    def test_preserve_missing_and_duplicate_payload_for_backend_idempotency(self):
        self.assertEqual(decode(self.topic,self.payload(),self.run),self.row)
        self.assertEqual(decode(self.topic,self.payload(),self.run),self.row)
        self.assertIsNone(decode(self.topic,self.payload(),self.run)["windX"])

    def test_cross_drone_run_and_unfinished_bucket_rejected(self):
        with self.assertRaises(ValueError): decode(self.topic.replace("sim-a","sim-b"),self.payload(),self.run)
        with self.assertRaises(ValueError): decode(self.topic,self.payload(),{**self.run,"runId":"other"})
        with self.assertRaises(ValueError): decode(self.topic,self.payload(),{**self.run,"status":"COMPLETED"})
        self.row["sourceTimeS"]=.5
        with self.assertRaises(ValueError): decode(self.topic,self.payload(),self.run)

    def test_ambiguous_nonfinite_and_oversized_json_rejected(self):
        for payload in ('{"x":1,"x":2}', '{"x":NaN}', " "*65537):
            with self.assertRaises(ValueError): decode(self.topic,payload,self.run)
        self.row["id"]=42
        with self.assertRaises(ValueError): decode(self.topic,self.payload(),self.run)


if __name__ == "__main__":
    unittest.main()
