# Multi-Tenant CMDB

A Configuration Management Database (CMDB) application with multi-tenant support, built with Python Flask and Docker.

## Features

- **Multi-Tenant Architecture**: Separate CMDB instances for different organizations
- **User Authentication**: Secure login/logout with password hashing
- **CI Types**: Define custom Configuration Item types per tenant
- **Configuration Items**: Track IT assets (servers, applications, networks, etc.)
- **Relationships**: Map dependencies between configuration items
- **Role-Based Access**: Admin and regular user roles
- **Web UI**: Clean, responsive interface
- **Docker Ready**: Easy deployment with Docker Compose

## Quick Start

### Using Docker Compose (Recommended)

1. **Clone the repository**
   ```bash
   cd sh-cmdb
   ```

2. **Configure environment (optional)**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

3. **Build and start**
   ```bash
   docker-compose up -d
   ```

4. **Access the application**
   - Open your browser: `http://localhost:5000`
   - Register a new account (creates a new tenant)

### Using Make

```bash
make build    # Build Docker image
make up       # Start containers
make logs     # View logs
```

### Manual Docker Commands

```bash
docker build -t sh-cmdb .
docker run -d -p 5000:5000 -v cmdb_data:/app/data --name cmdb sh-cmdb
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Multi-Tenant CMDB                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Tenant A          Tenant B          Tenant C               │
│  ┌────────────┐    ┌────────────┐    ┌────────────┐         │
│  │ Users      │    │ Users      │    │ Users      │         │
│  │ CI Types   │    │ CI Types   │    │ CI Types   │         │
│  │ Config Is  │    │ Config Is  │    │ Config Is  │         │
│  │ Relations  │    │ Relations  │    │ Relations  │         │
│  └────────────┘    └────────────┘    └────────────┘         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Data Models

### Tenant
- Organization/Company
- Isolated data per tenant

### User
- Username, email, password
- Tenant association
- Admin role

### CI Type (Configuration Item Type)
- Custom types per tenant (Server, Application, Network, etc.)

### Config Item
- Name, description, status
- Associated CI type
- JSON attributes for flexibility

### CI Relationship
- Dependencies between items
- Types: depends_on, hosted_on, connected_to, etc.

## Usage Guide

### 1. Register a New Organization

1. Click "Register" on the home page
2. Enter organization name, username, email, and password
3. The first user becomes an admin

### 2. Create CI Types

1. Navigate to "CI Types"
2. Click "+ New CI Type"
3. Define types like: Server, Application, Database, Network Device

### 3. Add Configuration Items

1. Navigate to "Config Items"
2. Click "+ New Config Item"
3. Fill in details and add JSON attributes

### 4. Create Relationships

1. View a Config Item
2. Click "Manage Relationships"
3. Add relationships to other items

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Home page |
| GET/POST | `/login` | User login |
| GET/POST | `/register` | User registration |
| GET | `/logout` | User logout |
| GET | `/dashboard` | Dashboard |
| GET/POST | `/ci-types` | List/Create CI Types |
| GET/POST | `/config-items` | List/Create Config Items |
| GET | `/config-items/<id>` | View Config Item |
| GET/POST | `/config-items/<id>/edit` | Edit Config Item |
| POST | `/config-items/<id>/delete` | Delete Config Item |
| GET/POST | `/config-items/<id>/relationships` | Manage Relationships |
| GET | `/admin/users` | List users (admin only) |
| GET/POST | `/admin/users/new` | Create user (admin only) |

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `dev-secret-key` | Flask secret key |
| `DATABASE_URL` | `sqlite:///cmdb.db` | Database connection string |

### Database Options

**SQLite (default)**:
```
DATABASE_URL=sqlite:////app/data/cmdb.db
```

**PostgreSQL**:
```
DATABASE_URL=postgresql://cmdb:password@postgres:5432/cmdb
```

## Development

### Run Locally (without Docker)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

### Project Structure

```
sh-cmdb/
├── app.py                 # Main application
├── requirements.txt       # Python dependencies
├── Dockerfile            # Docker image
├── docker-compose.yml    # Docker Compose config
├── templates/            # HTML templates
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html
│   ├── ci_types/
│   ├── config_items/
│   ├── admin/
│   └── errors/
└── data/                 # Database storage
```

## Security Notes

- Change `SECRET_KEY` in production
- Use HTTPS in production
- Regularly update dependencies
- Use strong passwords
- Consider adding rate limiting

## Troubleshooting

### Container won't start
```bash
docker-compose logs cmdb
```

### Database issues
```bash
make clean    # WARNING: Deletes all data
make up
```

### Port already in use
Edit `docker-compose.yml` and change the port mapping:
```yaml
ports:
  - "8080:5000"  # Use port 8080 instead of 5000
```

## License

MIT License

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

---

Built with ❤️ using Flask and Docker
