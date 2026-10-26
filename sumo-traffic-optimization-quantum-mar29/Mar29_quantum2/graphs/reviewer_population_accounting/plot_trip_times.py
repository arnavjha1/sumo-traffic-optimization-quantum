"""Plot completed-trip travel and full-trip waiting averages."""
import sys
from plot_common import make_figure

if __name__ == '__main__':
    make_figure([('completed_mean_travel_seconds','Completed-trip travel time (s)'),
                 ('completed_mean_waiting_seconds','Completed-trip waiting time (s)')],
                'figure_trip_times','Completed-trip travel and waiting',show='--show' in sys.argv)
