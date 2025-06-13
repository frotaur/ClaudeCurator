"""
    Scripts that run the claude curator server, using the config provided in the .env file.
    The github webhook must have been created. By default, logs are saved in the current directory, in 'curator_server_logs.txt'.
"""

import os
from curator_server import create_app
import argparse

def main():
    parser = argparse.ArgumentParser(description='Run the Claude Curator server')
    parser.add_argument('--log-dir', '-l', type=str, default='.', 
                       help='Directory for log files (empty string for no logging to file)')
    parser.add_argument('--print-log', '-p', action='store_true', 
                       help='Print log messages to console')
    
    curator_app = create_app(log_dir=parser.parse_args().log_dir, print_log=parser.parse_args().print_log)

    """Main entry point for the curator server"""
    curator_app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

if __name__ == '__main__':
    main()