"""Dijkstra oracle with its own graph traversal and directed edge arithmetic.

Shares the declared four-neighbour, constant-power physics assumption, not A*
or its implementation. This verifies software, not the physical flight model.
"""
import heapq
import math


def dijkstra_energy(grid,start,goal,airspeed,power):
    start,goal=tuple(start),tuple(goal);blocked=set(grid.blocked)
    if start in blocked or goal in blocked:return None
    costs={start:0.};queue=[(0.,start)]
    while queue:
        cost,point=heapq.heappop(queue)
        if cost!=costs[point]:continue
        if point==goal:return cost
        x,y=point
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
            other=(x+dx,y+dy)
            if not grid.contains(other) or other in blocked:continue
            midpoint=(x+dx/2,y+dy/2);wx=wy=0.
            for region in grid.wind_regions:
                if region.x_min<=midpoint[0]<=region.x_max and region.y_min<=midpoint[1]<=region.y_max:
                    wx,wy=region.vector
            parallel=wx*dx+wy*dy;cross=wy*dx-wx*dy
            if abs(cross)>=airspeed:continue
            speed=math.sqrt(airspeed**2-cross**2)+parallel
            if speed<=.25:continue
            candidate=cost+power*grid.cell_size_m/speed/3600
            if candidate<costs.get(other,math.inf):
                costs[other]=candidate;heapq.heappush(queue,(candidate,other))
    return None
