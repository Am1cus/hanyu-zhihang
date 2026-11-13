"""Read-only checks for a local evidence index. Uses only the standard library."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys


def fingerprint(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def resolve_file(workspace, relative):
    path = (workspace / relative).resolve()
    if not path.is_relative_to(workspace):
        raise ValueError('path outside workspace: ' + relative)
    return path


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def check_index(index, workspace):
    errors = []
    for relative, expected in index['files'].items():
        path = resolve_file(workspace, relative)
        if not path.is_file():
            errors.append(relative + ': missing')
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected:
            errors.append(relative + ': SHA-256 mismatch')
    if errors:
        return {'passed': False, 'errors': errors, 'samples': []}

    samples = []
    for group in index['experiments']:
        directory = resolve_file(workspace, group['directory'])
        frozen = read_json(directory / 'freeze.json')
        claimed = frozen.pop('freeze_sha256')
        if fingerprint(frozen) != claimed:
            errors.append(group['directory'] + ': invalid freeze fingerprint')
        rows = read_json(directory / 'results.json')
        records = {row['case_id']: row for row in rows['records']}
        with (directory / 'configurations.jsonl').open(encoding='utf-8') as file:
            specifications = {row['case_id']: row for row in map(json.loads, file)}
        if len(records) != group['executions'] or rows['freeze_sha256'] != claimed:
            errors.append(group['directory'] + ': result matrix differs')
        for case_id in group['samples']:
            record = records[case_id]
            with gzip.open(directory / record['archive'], 'rt', encoding='utf-8') as file:
                archive = json.load(file)
            checks = {
                'configuration': fingerprint(archive['configuration']) == record['configuration_sha256']
                    == specifications[case_id]['configuration_sha256'] == archive['configuration_sha256'],
                'summary': archive['summary'] == record['summary'],
                'result': archive['result_sha256'] == record['result_sha256'],
                'sources': all(frozen['source_sha256'].get(name) == digest
                               for name, digest in archive['metadata']['source_sha256'].items()
                               ),
            }
            # Runtime archives exclude computation time from the result hash.
            decisions = [{**decision, 'record': {
                name: value for name, value in decision['record'].items()
                if name != 'computation_ms'}} for decision in archive['decisions']]
            deterministic = {name: archive[name] for name in
                             ('summary', 'telemetry', 'events', 'intervals')}
            deterministic['decisions'] = decisions
            checks['result_recomputed'] = fingerprint(deterministic) == record['result_sha256']
            integral = sum(row['average_voltage_v'] * row['current_a'] * row['dt_s'] / 3600
                           for row in archive['telemetry'])
            checks['wh_integral'] = abs(integral - archive['summary']['consumed_wh']) < 1e-7
            if not all(checks.values()):
                errors.append(group['directory'] + '/' + case_id + ': sample mismatch')
            samples.append({'experiment': group['kind'], 'case_id': case_id, 'checks': checks})
    return {'passed': not errors, 'files_checked': len(index['files']),
            'errors': errors, 'samples': samples}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--index', required=True, type=Path)
    args = parser.parse_args()
    try:
        report = check_index(read_json(args.index), args.workspace.resolve())
    except (OSError, ValueError, KeyError, TypeError) as error:
        report = {'passed': False, 'errors': [str(error)]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
