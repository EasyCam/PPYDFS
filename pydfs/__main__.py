"""
Python Distributed File System (PYDFS) - Command Line Interface

This module allows running PYDFS components directly:
    python -m pydfs nameserver [web_port]
    python -m pydfs dataserver [host] [port] [storage_dir] [name_server]
"""

import sys
import os
import time
# Fix the import to use the Client class directly from pydfs module
from pydfs import start_name_server, start_data_server, Client

# rest of the file remains unchanged

def print_usage():
    """Print usage instructions"""
    print("Python Distributed File System (PYDFS)")
    print("\nUsage:")
    print("  python -m pydfs nameserver [web_port]")
    print("  python -m pydfs dataserver [host] [port] [storage_dir] [name_server]")
    print("  python -m pydfs client <command> [options]")
    print("\nExamples:")
    print("  python -m pydfs nameserver 8080")
    print("  python -m pydfs dataserver localhost 9001 ./storage localhost:9000")
    print("  python -m pydfs client upload myfile.txt")
    print("\nCommands:")
    print("  nameserver  - Start a name server with web monitoring interface")
    print("  dataserver  - Start a data server node")
    print("  client      - Execute client operations (upload, download, list, delete)")

def main():
    """Main entry point for the PYDFS command line interface"""
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)
        
    if sys.argv[1] == 'nameserver':
        web_port = 8080
        if len(sys.argv) > 2:
            try:
                web_port = int(sys.argv[2])
            except ValueError:
                print("Web port must be a number, using default 8080")
                
        print(f"Starting name server with web interface on port {web_port}")
        print(f"Access the monitoring dashboard at http://localhost:{web_port}")
        start_name_server(web_port)
        
    elif sys.argv[1] == 'dataserver':
        # Parse arguments for data server
        host = 'localhost'
        port = 9001
        storage_dir = 'data_storage'
        name_server = 'localhost:9000'
        
        if len(sys.argv) > 2:
            host = sys.argv[2]
        if len(sys.argv) > 3:
            try:
                port = int(sys.argv[3])
            except ValueError:
                print(f"Port must be a number, using default {port}")
        if len(sys.argv) > 4:
            storage_dir = sys.argv[4]
        if len(sys.argv) > 5:
            name_server = sys.argv[5]
            
        print(f"Starting data server on {host}:{port}")
        print(f"Storage directory: {os.path.abspath(storage_dir)}")
        print(f"Connecting to name server: {name_server}")
        start_data_server(host, port, storage_dir, name_server)
        
    elif sys.argv[1] == 'client':
        # Client operations
        if len(sys.argv) < 3:
            print("Client usage:")
            print("  python -m pydfs client upload <local_file> [remote_name]")
            print("  python -m pydfs client download <remote_file> [local_path]")
            print("  python -m pydfs client list")
            print("  python -m pydfs client delete <remote_file>")
            sys.exit(1)
        
        name_server = 'localhost:9000'
        if len(sys.argv) > 5:
            name_server = sys.argv[5]
            
        client = Client(name_server)
        
        if sys.argv[2] == 'upload':
            if len(sys.argv) < 4:
                print("Error: Missing local file path")
                sys.exit(1)
                
            local_path = sys.argv[3]
            remote_name = sys.argv[4] if len(sys.argv) > 4 else None
            
            print(f"Uploading {local_path} to PYDFS...")
            if client.upload_file(local_path, remote_name):
                print("Upload successful")
            else:
                print("Upload failed")
                
        elif sys.argv[2] == 'download':
            if len(sys.argv) < 4:
                print("Error: Missing remote file name")
                sys.exit(1)
                
            remote_file = sys.argv[3]
            local_path = sys.argv[4] if len(sys.argv) > 4 else remote_file
            
            print(f"Downloading {remote_file} from PYDFS...")
            if client.download_file(remote_file, local_path):
                print(f"Download successful: {local_path}")
            else:
                print("Download failed")
                
        elif sys.argv[2] == 'list':
            print("Files in PYDFS:")
            files = client.list_files()
            if files:
                for file in files:
                    created = time.strftime("%Y-%m-%d %H:%M:%S", 
                                           time.localtime(file.get('created', 0)))
                    print(f"- {file['filename']} ({file['size']} bytes, created: {created})")
            else:
                print("No files found")
                
        elif sys.argv[2] == 'delete':
            if len(sys.argv) < 4:
                print("Error: Missing remote file name")
                sys.exit(1)
                
            remote_file = sys.argv[3]
            if client.delete_file(remote_file):
                print(f"File {remote_file} deleted successfully")
            else:
                print(f"Failed to delete {remote_file}")
        else:
            print(f"Unknown client command: {sys.argv[2]}")
            sys.exit(1)
            
    else:
        print(f"Unknown command: {sys.argv[1]}")
        print_usage()
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nShutdown requested, exiting...")
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)