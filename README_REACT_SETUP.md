# MCP Gateway Registry - React Frontend

This project has been refactored to use a modern React frontend with TypeScript and Tailwind CSS.

## Architecture

- **Backend**: FastAPI (Python) - serves API endpoints and static React build
- **Frontend**: React + TypeScript + Tailwind CSS
- **Deployment**: Docker with automatic frontend build

## Development

### Running with Docker (Production-like)
```bash
# Build and run the complete stack
docker build -f docker/Dockerfile.registry -t mcp-gateway-registry .
docker run -p 7860:7860 -e ADMIN_PASSWORD=your_secure_password mcp-gateway-registry
```

### Local Development
For faster development, you can run the frontend and backend separately:

#### Backend (FastAPI)
```bash
cd registry
uvicorn main:app --host 0.0.0.0 --port 7860 --reload
```

#### Frontend (React)
```bash
cd frontend
npm install
npm start  # Runs on http://localhost:3000
```

The React dev server will proxy API requests to the FastAPI backend on port 7860.

## Features

### Modern UI Components
- ✅ User dropdown with "Generate Token" option
- ✅ Clean sidebar with filters and statistics  
- ✅ Modern card-based server grid
- ✅ Dark/light theme toggle
- ✅ Responsive mobile design
- ✅ Loading states and error handling

### Architecture Benefits
- ✅ Component-based and maintainable code
- ✅ TypeScript for type safety
- ✅ Tailwind CSS for consistent styling
- ✅ React Router for client-side navigation
- ✅ Context providers for global state
- ✅ Proper separation of concerns

## API Integration

The React frontend communicates with the FastAPI backend via REST APIs:

- `GET /api/auth/me` - Get current user info
- `GET /api/servers` - Get server list
- `POST /api/servers/{path}/toggle` - Toggle server enabled/disabled
- `POST /api/auth/generate-token` - Generate JWT tokens
- `GET /api/servers/stats` - Get server statistics

## File Structure

```
frontend/
├── src/
│   ├── components/       # Reusable UI components
│   ├── contexts/         # React contexts (Auth, Theme)
│   ├── hooks/           # Custom React hooks
│   ├── pages/           # Page components
│   └── App.tsx          # Main app component
├── public/              # Static assets
└── package.json         # Dependencies and scripts
```

## Docker Build Process

The Docker build process:
1. Installs Node.js 20
2. Builds the React frontend (`npm run build`)
3. Sets up Python environment
4. Configures FastAPI to serve the built React app
5. Sets up Nginx reverse proxy

## Migration Notes

The old template-based UI has been completely replaced with:
- Modern React components instead of 2700+ line HTML files
- Component-based architecture instead of monolithic templates
- TypeScript for better developer experience
- Tailwind CSS for consistent, maintainable styling
- Client-side routing instead of server-side redirects

This makes the codebase much more maintainable and provides a better user experience. 