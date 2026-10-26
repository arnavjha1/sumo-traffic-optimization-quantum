"""Plot accumulated network-wide time loss and stopped waiting, including unfinished trips."""
import sys
from plot_common import make_figure

if __name__ == '__main__':
    make_figure([('network_time_loss_seconds','Accumulated time loss (vehicle-s)'),
                 ('network_waiting_seconds','Accumulated stopped waiting (vehicle-s)')],
                'figure_network_delay','Network-wide delay and waiting',show='--show' in sys.argv)
