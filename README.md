# PYDFS - Python Distributed File System

PYDFS is a lightweight distributed file system implemented in Python. It provides a reliable way to store and access files across multiple server nodes with automatic replication and failure recovery.

## Features

- **Distributed Storage**: Files are split into blocks and distributed across multiple data servers
- **Data Replication**: Configurable replication factor ensures data redundancy and availability
- **Fault Tolerance**: Automatic block re-replication when servers fail
- **Web Monitoring Interface**: Real-time monitoring of system status and file distribution
- **Command Line Interface**: Easy-to-use commands for system management and file operations

## Architecture

PYDFS consists of three main components:

1. **Name Server**: Manages file metadata and coordinates data servers
2. **Data Servers**: Store the actual file blocks with replication
3. **Client**: Interface for users to upload, download, and manage files

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Starting a Name Server

```bash
python -m pydfs nameserver [web_port]
```

Example:

```bash
python -m pydfs nameserver 8080
```

This starts a name server with a web monitoring interface accessible at http://localhost:8080.

### Starting a Data Server

```bash
python -m pydfs dataserver [host] [port] [storage_dir] [name_server]
```

Example:
```bash
python -m pydfs dataserver localhost 9001 ./storage localhost:9000
```

### Client Operations

#### Upload a file

```bash
python -m pydfs client upload myfile.txt [remote_name]
```

#### Download a file

```bash
python -m pydfs client download remote_file [local_path]
```

#### List all files

```bash
python -m pydfs client list
```

#### Delete a file

```bash
python -m pydfs client delete remote_file
```

## Web Interface

The web interface provides:

- Real-time monitoring of data servers
- File upload/download functionality
- File and block management
- System status information

## Configuration

Default settings:
- Name server port: 9000
- Web interface port: 8080
- Replication factor: 2
- Block size: 4MB


## License

GPLv3