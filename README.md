⚡ Cybersecurity Simulation for Smart Grids
📌 Overview

This project is a cybersecurity simulation platform for smart electrical grids within a smart city environment. It demonstrates how modern power systems are vulnerable to cyber threats and how different security mechanisms can detect and mitigate these attacks in real time.

The system integrates a Python-based control & attacker dashboard with a Unity-based smart city simulation, communicating through a cloud backend (Firebase) to enable real-time interaction.
🎯 Objectives

    Simulate real-world cyber attacks on smart grids

    Visualize the impact of attacks in a smart city environment

    Implement and evaluate cybersecurity defense mechanisms

    Provide a safe platform for learning and experimentation

⚙️ System Architecture

The project consists of three main components:

    Attacker & Control Dashboard (Python - Tkinter)

        Launches cyber attacks

        Monitors grid data

        Displays system logs and responses

    Smart City Simulation (Unity)

        Visualizes grid infrastructure

        Shows real-time impact of attacks (blackouts, delays, failures)

    Cloud Backend (Firebase Realtime Database)

        Handles communication between dashboard and simulation

        Stores grid status and command data

🚨 Simulated Cyber Attacks

The platform supports multiple attack scenarios:

    DDoS Flood Attack – Overloads the system causing delays or failure

    Blackout Attack – Disrupts power supply across regions

    Targeted Blackout – Affects specific meters or locations

    Meter Tampering – Alters energy consumption data

    Replay Attack – Reuses previously valid commands

    Man-in-the-Middle (MITM) – Intercepts and modifies communication

    Load Spike / Instability Attacks – Creates abnormal grid behavior

🛡️ Security Mechanisms

To defend against attacks, the system includes:

    Authentication System – Verifies valid commands

    Data Integrity (Hashing) – Detects tampered data

    Replay Protection – Uses timestamps to block duplicate requests

    Anomaly Detection – Identifies unusual system behavior

    Firewall / Defense Logic – Blocks unauthorized actions

🔄 Working Principle

    The dashboard sends commands (normal or malicious) to Firebase

    The Unity simulation reads these commands and updates the smart city

    The system visualizes the impact of attacks in real time

    Security mechanisms analyze and respond to threats

    Results and logs are displayed on the dashboard

🧠 Key Features

    Real-time cyber attack simulation

    Interactive smart city visualization

    Multi-layer cybersecurity defense system

    Attack vs defense analysis

    Educational and research-focused design

💡 Applications

    Smart grid cybersecurity research

    Training and awareness programs

    Academic demonstrations

    Testing defense strategies in a safe environment

🚀 Future Enhancements

    Integration of Machine Learning for advanced anomaly detection

    Real-world data integration

    Scalable distributed architecture

    Enhanced visualization and analytics

📌 Conclusion

This project provides a practical and interactive platform to understand the cybersecurity challenges of smart grids and evaluate defense strategies, helping build more secure and resilient power systems.
