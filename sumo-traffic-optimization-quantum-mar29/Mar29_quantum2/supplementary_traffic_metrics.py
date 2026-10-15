"""Whole-network metrics from SUMO tripinfo, including unfinished trips.

timeLoss measures seconds lost relative to each vehicle's ideal speed; it is
not the same as stopped waiting time. Insertion waiting is reported separately.
"""
import json
import os
from pathlib import Path
import uuid
import xml.etree.ElementTree as ET


def summarize_tripinfo(path):
    groups = {'completed': [], 'unfinished': [], 'removed': []}
    undeparted = 0
    for _, element in ET.iterparse(path, events=('end',)):
        if element.tag != 'tripinfo':
            continue
        a = element.attrib
        if float(a['depart']) < 0:
            undeparted += 1
        else:
            # SUMO marks vehicles flushed at the horizon as vaporized="end".
            # They are unfinished trips, not removals during the simulation.
            removed = a.get('vaporized', '') not in ('', '0', 'false', 'end')
            group = 'removed' if removed else ('completed' if float(a['arrival']) >= 0 else 'unfinished')
            groups[group].append({k: float(a[k]) for k in
                                  ('timeLoss', 'waitingTime', 'duration', 'departDelay')})
        element.clear()
    result = {'schema_version': 1, 'undeparted_tripinfo_records': undeparted}
    for name, rows in groups.items():
        result[name + '_trips'] = len(rows)
        result[name + '_time_loss_seconds'] = sum(r['timeLoss'] for r in rows)
        result[name + '_waiting_seconds'] = sum(r['waitingTime'] for r in rows)
    entered = [r for rows in groups.values() for r in rows]
    result['departed_trips'] = len(entered)
    result['network_time_loss_seconds'] = sum(r['timeLoss'] for r in entered)
    result['network_waiting_seconds'] = sum(r['waitingTime'] for r in entered)
    result['departed_insertion_delay_seconds'] = sum(r['departDelay'] for r in entered)
    completed = groups['completed']
    result['completed_mean_travel_seconds'] = (sum(r['duration'] for r in completed) / len(completed)
                                                if completed else None)
    result['completed_mean_waiting_seconds'] = (sum(r['waitingTime'] for r in completed) / len(completed)
                                                 if completed else None)
    return result


class SupplementaryMetrics:
    def __init__(self, label):
        directory = Path(os.environ.get('SUPPLEMENTARY_OUTPUT_DIR',
                         Path(__file__).resolve().parent / 'supplementary_traffic_results'))
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / (label + '_' + uuid.uuid4().hex[:12] + '.tripinfo.xml')
        self.departed = self.arrived = self.teleports = 0
        self.pending_seconds = 0.0
        self.last_time = 0.0

    def sumo_args(self):
        return ['--tripinfo-output', str(self.path.resolve()),
                '--tripinfo-output.write-unfinished', 'true',
                '--tripinfo-output.write-undeparted', 'true']

    def step(self, traci):
        now = traci.simulation.getTime()
        self.departed += traci.simulation.getDepartedNumber()
        self.arrived += traci.simulation.getArrivedNumber()
        self.teleports += traci.simulation.getStartingTeleportNumber()
        # Discrete right-endpoint integral, separate from in-network time loss.
        self.pending_seconds += len(traci.simulation.getPendingVehicles()) * (now - self.last_time)
        self.last_time = now

    def snapshot(self, traci):
        self.endpoint = {
            'cutoff_seconds': traci.simulation.getTime(),
            'active_vehicles_at_cutoff': traci.vehicle.getIDCount(),
            'pending_insertion_at_cutoff': len(traci.simulation.getPendingVehicles()),
            'pending_insertion_vehicle_seconds_sampled': self.pending_seconds,
            'teleport_start_events': self.teleports,
            'departed_events': self.departed, 'arrived_events': self.arrived,
        }

    def finish(self):
        # Call only after traci.close(), when SUMO has flushed unfinished records.
        result = {**summarize_tripinfo(self.path), **self.endpoint,
                  'tripinfo_path': str(self.path.resolve())}
        result['departure_accounting_ok'] = result['departed_trips'] == self.departed
        result['arrival_accounting_ok'] = result['completed_trips'] == self.arrived
        result['completion_fraction_of_departed'] = (result['completed_trips'] / self.departed
                                                     if self.departed else None)
        self.path.with_suffix('.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print('SUPPLEMENTARY_JSON: ' + json.dumps(result))
        return result
