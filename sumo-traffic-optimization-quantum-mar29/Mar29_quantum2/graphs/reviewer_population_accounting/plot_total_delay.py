"""Pre-entry delay from all tripinfo records and its sum with in-network time loss."""
import sys
from plot_common import make_figure
if __name__=='__main__':
    make_figure([('all_insertion_delay_seconds','Total pre-entry delay (vehicle-s)'),
                 ('time_loss_plus_insertion_delay_seconds','Time loss + pre-entry delay (vehicle-s)')],
                 'figure_total_delay','Including demand awaiting insertion',show='--show' in sys.argv)
