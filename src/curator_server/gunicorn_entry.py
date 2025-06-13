from curator_server import create_app
import os

log_dir = os.environ.get('CURATOR_LOG_DIR', '.')
print_log = os.environ.get('CURATOR_PRINT_LOG', '0') == '1'

app = create_app(log_dir=log_dir, print_log=print_log)