# OATS Framework UI

**O**bserve · **A**dapt · **T**akeAction · **S**ynthesize

Frontend React application for the OATS Framework - an autonomous SRE agent for diagnosing and resolving infrastructure failures.

## Overview

The OATS Framework UI provides a real-time interface for interacting with the OATS agent, visualizing the investigation process, and monitoring infrastructure diagnostics.

## Features

- **Real-time Investigation Tracking**: Live updates as the OATS agent progresses through analysis
- **Interactive Interface**: Submit infrastructure problems and receive guided diagnostics
- **WebSocket Communication**: Instant feedback from the agent's thought process, actions, and observations
- **Investigation History**: View previous analyses and their outcomes
- **Status Monitoring**: Connection status and investigation progress indicators

## Tech Stack

- **React 18.3.1** - Modern UI framework
- **Socket.io Client** - Real-time bidirectional communication
- **React Scripts 5.0.1** - Build and development tooling
- **CSS3** - Custom styling with dark theme

## Getting Started

### Prerequisites
- Node.js 14+ and npm
- OATS backend service running (see main README.md)

### Installation

```bash
# Navigate to the UI directory
cd services/ui

# Install dependencies
npm install
```

### Development

```bash
# Start the development server (runs on port 3000)
npm start
```

The UI will automatically connect to the backend service via proxy configuration.

### Build

```bash
# Create production build
npm run build
```

## Architecture

The OATS Framework UI follows a simple but effective architecture:

```
User Input → WebSocket → Backend API → OATS Agent
                ↓
         Real-time Updates → UI Display
```

### Key Components

- **App.js**: Main application component managing WebSocket connections and state
- **Message Handler**: Formats agent messages (thoughts, actions, observations, completion)
- **Connection Manager**: Handles WebSocket lifecycle and reconnection
- **Input Form**: Accepts infrastructure problem descriptions and initiates analysis

## OATS Framework Phases

The UI visualizes the agent's progress through the OATS cycle:

1. **Observe**: Gathering system information and metrics
2. **Adapt**: Analyzing data and forming hypotheses
3. **TakeAction**: Executing diagnostic tools and tests
4. **Synthesize**: Compiling results and providing recommendations

## Configuration

The UI connects to the backend via proxy configuration in `package.json`:

```json
"proxy": "http://localhost:8000"
```

Update this if your backend runs on a different port.

## Message Types

The UI handles various message types from the agent:

- `thought`: Agent's reasoning and analysis
- `action`: Tools being executed with parameters
- `observation`: Results from tool execution
- `finish`: Investigation completion with summary
- `status`: Status updates and progress indicators
- `error`: Error messages and diagnostics

## Styling

The UI uses a dark theme optimized for SRE work:
- Dark background (#1e1e1e, #282c34)
- Syntax highlighting colors for different message types
- Clear visual distinction between user input and agent responses
- Responsive design for various screen sizes

## Future Enhancements

- [ ] Investigation history browser
- [ ] Advanced visualization of causal chains
- [ ] Timeline reconstruction view
- [ ] Layer status dashboard
- [ ] Export investigation reports
- [ ] Multi-agent coordination view
- [ ] Real-time metrics integration
