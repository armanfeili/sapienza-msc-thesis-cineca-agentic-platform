# README_Cineca-Agentic-Platform_ui_control_panel

## Overview

The `ui_control_panel` is a comprehensive Streamlit-based web application that serves as the administrative control panel for the Cineca Agentic Platform. It provides a unified interface for managing all aspects of the platform, including authentication, agent runs, job monitoring, model providers, tenant administration, tool invocation, and system health monitoring.

## Architecture

### Core Components

#### Main Application (`app.py`)
- **Lines**: 441 lines
- **Function**: Main Streamlit application entry point
- **Features**:
  - Responsive design with tab-based navigation
  - Authentication flow with role-based access control
  - Session state management with token persistence
  - Auto-refresh capabilities with debounced polling
  - Error handling and user feedback
  - Developer mode for advanced features

#### API Client (`api.py`)
- **Lines**: 785 lines
- **Function**: Comprehensive HTTP client for platform API integration
- **Features**:
  - Auth0 token management with automatic renewal
  - Request normalization and error handling
  - Comprehensive endpoint wrappers for all platform APIs
  - Retry logic with exponential backoff
  - Response caching and optimization
  - Developer mode support for internal endpoints

#### State Management (`state.py`)
- **Lines**: 283 lines
- **Function**: Typed session state management
- **Features**:
  - Token lifecycle management with persistence
  - Tenant context handling
  - UI preferences and settings
  - Session validation and cleanup
  - Type-safe state operations

#### Utilities (`utils.py`)
- **Function**: Utility functions for common operations
- **Features**:
  - Jittered polling for auto-refresh
  - Exponential backoff calculations
  - Common helper functions

### Components (16 Modules)

#### Authentication & Security
- **`auto_renew.py`**: Token renewal management with automatic refresh
- **`token_badges.py`**: Authentication status display with scope visualization
- **`scope_checker.py`**: Permission validation and access control

#### User Interface
- **`confirm_modal.py`**: Confirmation dialogs for destructive operations
- **`error_display.py`**: Comprehensive error handling and display
- **`global_banner.py`**: System-wide notifications and alerts
- **`pagination.py`**: Data pagination with configurable page sizes
- **`table.py`**: Data table rendering with sorting and filtering

#### Data Visualization
- **`json_drawer.py`**: JSON data visualization with expandable views
- **`log_pane.py`**: Log display with filtering and search
- **`log_viewer.py`**: Advanced log analysis with real-time updates
- **`timeline.py`**: Event timeline visualization

#### Specialized Components
- **`health_cards.py`**: Health status indicators with color coding
- **`tenant_selector.py`**: Multi-tenant context switching
- **`tool_card.py`**: Tool interface cards with capability badges

### Views (10 Modules)

#### Core Management
- **`auth.py`** (457 lines): Authentication management with token operations
- **`agents.py`** (1000 lines): Agent run management and session monitoring
- **`jobs.py`** (579 lines): Job lifecycle management with admin controls

#### Data Exploration
- **`explore.py`** (226 lines): API exploration with interactive documentation
- **`cypher.py`** (460 lines): Natural language to Cypher query interface
- **`models.py`** (1107 lines): Model instance and provider management

#### Administrative Functions
- **`admin.py`** (833 lines): System administration with process management
- **`tenants.py`** (191 lines): Tenant lifecycle management
- **`tools.py`** (847 lines): Tool discovery and invocation with schema-driven forms

#### Monitoring
- **`dashboard.py`**: System health monitoring with auto-refresh

## Configuration

### Requirements (`requirements.txt`)
```txt
streamlit>=1.31.0
requests>=2.31.0
PyJWT>=2.8.0
pandas>=2.0.0
humanize>=4.7.0
python-dotenv>=1.0.0
```

### Streamlit Configuration (`.streamlit/config.toml`)
```toml
[server]
headless = true
port = 8501

[browser]
gatherUsageStats = false

[theme]
base = "light"
```

### Docker Setup
- **`Dockerfile`**: Multi-stage build with Python 3.11
- **`docker-compose.yml`**: Container orchestration with health checks
- **`setup.sh`**: Environment setup script

### Development Configuration
- **`.gitignore`**: Python and Streamlit-specific exclusions
- **`README.md`**: Existing documentation

## API Integration

### Authentication Flow
1. **Token Acquisition**: Auth0 integration with multiple token types (Admin/User/Machine)
2. **Token Renewal**: Automatic renewal with configurable intervals
3. **Scope Validation**: Role-based access control with scope checking
4. **Session Management**: Persistent sessions with cleanup

### Endpoint Coverage
The API client provides comprehensive wrappers for:
- **Authentication**: Token operations and user management
- **Agents**: Run creation, monitoring, and session management
- **Jobs**: Lifecycle management with status tracking
- **Models**: Provider and instance management
- **Tenants**: Multi-tenant operations
- **Tools**: Discovery, invocation, and schema management
- **Health**: System monitoring and diagnostics
- **Database**: Direct database operations and queries

### Error Handling
- **Retry Logic**: Exponential backoff for transient failures
- **Error Classification**: User-friendly error messages
- **Fallback Behavior**: Graceful degradation on API failures
- **Logging**: Comprehensive error tracking with context

## User Interface

### Navigation Structure
- **Tab-based Layout**: Organized by functional areas
- **Responsive Design**: Mobile-friendly interface
- **Context Awareness**: Dynamic UI based on user permissions
- **State Persistence**: Session state preservation across refreshes

### Key Features
- **Real-time Updates**: Auto-refresh with configurable intervals
- **Interactive Forms**: Schema-driven form generation
- **Data Visualization**: Tables, charts, and JSON viewers
- **Export Capabilities**: CSV/JSON export for data tables
- **Search & Filtering**: Advanced filtering across all data views

### Accessibility
- **Keyboard Navigation**: Full keyboard support
- **Screen Reader**: Semantic HTML structure
- **Color Coding**: Consistent status indicators
- **Loading States**: Progress indicators for long operations

## Security

### Authentication
- **Auth0 Integration**: Industry-standard authentication provider
- **Multi-token Support**: Admin, User, and Machine tokens
- **Token Scoping**: Granular permission system
- **Secure Storage**: Encrypted token persistence

### Authorization
- **Role-based Access**: Admin/User/Machine roles
- **Scope Checking**: Capability-based permissions
- **API Security**: Request signing and validation
- **Audit Logging**: Comprehensive security event tracking

### Data Protection
- **Sensitive Data Masking**: Automatic redaction in logs and displays
- **Input Validation**: Schema-based input validation
- **SQL Injection Prevention**: Parameterized queries
- **XSS Protection**: HTML sanitization

## Performance

### Optimization Techniques
- **Lazy Loading**: On-demand data fetching
- **Caching**: Response caching with TTL
- **Debounced Updates**: Prevented excessive API calls
- **Pagination**: Efficient large dataset handling
- **Background Processing**: Non-blocking operations

### Monitoring
- **Health Checks**: Real-time system health monitoring
- **Performance Metrics**: Response time tracking
- **Error Rates**: Failure rate monitoring
- **Resource Usage**: Memory and CPU monitoring

## Development

### Code Organization
- **Modular Architecture**: Separated concerns with clear boundaries
- **Type Hints**: Comprehensive type annotations
- **Documentation**: Inline documentation and docstrings
- **Testing**: Unit and integration test support

### Developer Features
- **Developer Mode**: Advanced debugging capabilities
- **Internal Endpoints**: Direct API access for development
- **Debug Logging**: Enhanced logging in development
- **Hot Reload**: Streamlit's automatic reload on changes

### Deployment
- **Containerized**: Docker-based deployment
- **Health Checks**: Container health monitoring
- **Environment Configuration**: Flexible environment setup
- **Scalability**: Horizontal scaling support

## Usage

### Getting Started
1. **Environment Setup**: Run `setup.sh` for initial configuration
2. **Dependencies**: Install requirements with `pip install -r requirements.txt`
3. **Configuration**: Set environment variables and Auth0 credentials
4. **Launch**: Run `streamlit run app.py`

### User Workflows

#### Agent Management
1. Navigate to Agents tab
2. View active agent runs
3. Monitor session status
4. Cancel or modify runs as needed

#### Model Administration
1. Access Models & Providers tab
2. Configure default model instances
3. Register new providers
4. Test model instances

#### System Monitoring
1. Dashboard tab for health overview
2. Admin tab for detailed system information
3. Process management and log viewing

#### Tool Operations
1. Tools tab for discovery
2. Schema-driven invocation forms
3. Result visualization and export

### Administrative Tasks
- **Tenant Management**: Create and manage tenant contexts
- **User Administration**: Role and permission management
- **System Maintenance**: Process monitoring and database operations
- **Manifest Management**: Built-in manifest lifecycle

## Troubleshooting

### Common Issues
- **Authentication Failures**: Check token validity and scopes
- **API Timeouts**: Verify network connectivity and API health
- **Permission Errors**: Confirm user roles and required scopes
- **Performance Issues**: Check system resources and database health

### Debugging
- **Developer Mode**: Enable for additional debugging information
- **Log Analysis**: Use log viewer for detailed error information
- **Health Checks**: Monitor component health status
- **Network Tools**: Verify API connectivity and responses

### Support
- **Documentation**: Comprehensive inline documentation
- **Error Messages**: Detailed error reporting with context
- **Audit Logs**: Complete operation history
- **Health Monitoring**: Real-time system status

## Architecture Decisions

### Streamlit Framework
- **Rationale**: Rapid web application development with Python
- **Benefits**: Fast prototyping, rich component ecosystem
- **Trade-offs**: Single-threaded execution, state management complexity

### Modular Component Design
- **Rationale**: Reusable UI components with consistent behavior
- **Benefits**: Maintainability, consistency, rapid development
- **Implementation**: Component library with standardized interfaces

### API Client Architecture
- **Rationale**: Centralized API interaction with error handling
- **Benefits**: Consistent error handling, retry logic, caching
- **Features**: Automatic token renewal, request normalization

### State Management
- **Rationale**: Complex application state requires structured management
- **Benefits**: Type safety, persistence, validation
- **Implementation**: Custom state management with Streamlit session state

### Authentication Integration
- **Rationale**: Auth0 provides enterprise-grade authentication
- **Benefits**: Security, scalability, feature-rich
- **Implementation**: Multi-token support with automatic renewal

## Future Enhancements

### Planned Features
- **Advanced Analytics**: Enhanced monitoring and reporting
- **Workflow Automation**: Automated administrative tasks
- **API Versioning**: Support for multiple API versions
- **Plugin Architecture**: Extensible component system

### Performance Improvements
- **Caching Layer**: Enhanced response caching
- **Background Jobs**: Asynchronous processing
- **Database Optimization**: Query optimization and indexing
- **CDN Integration**: Static asset optimization

### Security Enhancements
- **MFA Support**: Multi-factor authentication
- **Audit Trails**: Enhanced security logging
- **Compliance**: Regulatory compliance features
- **Encryption**: End-to-end encryption support

This comprehensive control panel serves as the central nervous system for the Cineca Agentic Platform, providing administrators and users with powerful tools to manage, monitor, and optimize the entire system.</content>
<parameter name="filePath">/Users/armanfeili/Arman/Sapienza Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform/docs/general/README_Cineca-Agentic-Platform_ui_control_panel.md