"""Plot vehicles pending insertion and the separately measured insertion backlog integral."""
import sys
from plot_common import make_figure

if __name__ == '__main__':
    make_figure([('pending_insertion_at_cutoff','Vehicles pending insertion'),
                 ('pending_insertion_vehicle_seconds_sampled','Insertion backlog integral (vehicle-s)')],
                'figure_insertion_backlog','Demand awaiting network entry',show='--show' in sys.argv)
