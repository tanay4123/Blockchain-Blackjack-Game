\# Blockchain-Backed Blackjack Game



Distributed blockchain-backed payment system for multiplayer Blackjack with real-time WebSocket communication.



\## Features



\- Asynchronous Python backend using aiohttp and asyncio

\- WebSocket-based real-time game state updates

\- Blockchain validation for signed transactions

\- Fork resolution and liveness checks

\- HTML/JavaScript frontend

\- Tested with 100+ networked agents in VM environment



\## Architecture

```

┌─────────────┐     WebSocket      ┌──────────────┐

│   Frontend  │ ←─────────────────→ │  Game Server │

│  (HTML/JS)  │                     │   (game.py)  │

└─────────────┘                     └──────────────┘

&nbsp;                                          │

&nbsp;                                          ↓

&nbsp;                                   ┌──────────────┐

&nbsp;                                   │  Blockchain  │

&nbsp;                                   │  Network     │

&nbsp;                                   └──────────────┘

```



\## Tech Stack



\- \*\*Backend\*\*: Python, aiohttp, asyncio, WebSockets

\- \*\*Frontend\*\*: HTML, JavaScript

\- \*\*Blockchain\*\*: Custom implementation with cryptographic validation

\- \*\*Networking\*\*: Distributed consensus with fork resolution



\## Project Structure



\- `blockchain/` - Blockchain implementation and network agent

\- `game/` - Blackjack game server with WebSocket API

\- `frontend/` - Web-based user interface



\## Technical Highlights



\- \*\*Async I/O\*\*: High-performance concurrent connection handling

\- \*\*Consensus Protocol\*\*: Longest-chain rule with fork resolution

\- \*\*Transaction Validation\*\*: Cryptographic signing and verification

\- \*\*Real-time Communication\*\*: WebSocket protocol for instant updates



\## Author



Tanay Agrawal - \[LinkedIn](https://linkedin.com/in/tanay-agrawal-1bb5711ba) - \[GitHub](https://github.com/tanay4123)

