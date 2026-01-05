# Blockchain-Backed Blackjack Game

Distributed blockchain-backed payment system for multiplayer Blackjack with real-time WebSocket communication.

## My Contributions

This project was developed as part of CS 340 Intro to Computer Systems at UIUC. The core blockchain and game logic components I implemented include:

**Blockchain Implementation (`blockchain/blockchain.py`):**
- Block validation and cryptographic transaction verification
- Fork resolution algorithm using longest-chain rule
- Distributed consensus mechanism
- Account balance tracking and state management
- Liveness checks for on-chain payment confirmation

**Game Logic (`game/game.py`):**
- Blackjack game rules and state management
- Player hand evaluation and game flow
- Betting system and payout logic
- Integration with blockchain for secure transactions

**Network Agent (`blockchain/bc_agent.py`):**
- Distributed network communication protocol
- Block propagation and synchronization
- Peer-to-peer networking for decentralized consensus

*Note: WebSocket infrastructure, HTTP routing, and async server setup were provided by CS 340 course staff to support the distributed systems implementation.*

## Features

- Asynchronous Python backend using aiohttp and asyncio
- WebSocket-based real-time game state updates
- Blockchain validation for signed transactions
- Fork resolution and liveness checks
- HTML/JavaScript frontend
- Tested with 100+ networked agents in VM environment

## Architecture