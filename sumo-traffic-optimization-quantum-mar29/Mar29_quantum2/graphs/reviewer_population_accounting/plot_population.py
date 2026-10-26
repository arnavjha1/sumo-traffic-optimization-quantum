"""Plot completed and unfinished trips. Run with --show for an interactive window."""
import sys
from plot_common import make_figure

if __name__ == '__main__':
    make_figure([('completed_trips','Completed trips'),('unfinished_trips','Unfinished trips at cutoff')],
                'figure_population','Vehicle populations',show='--show' in sys.argv)
