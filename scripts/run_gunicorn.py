import os
import subprocess
from dotenv import load_dotenv
import argparse


def main():
    load_dotenv()  # Load environment variables from .env file
    parser = argparse.ArgumentParser(description='Run the Claude Curator server with gunicorn')
    parser.add_argument('--log-dir', '-l', type=str, default='./logs', 
                        help='Directory for log files')
    parser.add_argument('--print-log', '-p', action='store_true', 
                        help='Print log messages to console')
    args = parser.parse_args()

    env = os.environ.copy()
    env['CURATOR_LOG_DIR'] = args.log_dir
    env['CURATOR_PRINT_LOG'] = '1' if args.print_log else '0'

    # Run the gunicorn server
    subprocess.run(['gunicorn', '-w', '1', '-b', f'0.0.0.0:{os.environ.get("PORT", 5000)}', 'curator_server.gunicorn_entry:app'], env=env)

if __name__ == '__main__':
    main()