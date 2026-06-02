# Lofi Girl on Steroids ##### (kinda)

## Problem Definition

Maintaining focus during learning or work is difficult, and people often do not notice immediately when their attention starts to drift. This can reduce productivity, learning efficiency and overall performance. Traditional feedback methods, such as self-reflection or productivity tracking, usually rely on manual input and only provide information after the loss of focus has already happened.

Our project addresses this challenge by exploring how EEG brain signal data can be used to detect changes in cognitive state in real time. The system analyzes EEG frequency bands and classifies the user’s current state as either focused or drifting. By providing immediate feedback, the project aims to help users become more aware of their attention level and support better focus management during tasks.

The main user need is a lightweight and responsive way to recognize focus changes without requiring constant self-monitoring. This project is an experimental prototype and is not intended as a medical or diagnostic tool, but as a proof of concept for real-time neurofeedback-based focus awareness.


## Value & Impact

This project has value because it gives users immediate feedback about their cognitive state while they are working or learning. Instead of relying on self-reflection after a task is finished, the system attempts to detect focus changes in real time using EEG data. This can help users become more aware of moments when their attention decreases and support better focus management.

The potential impact is especially relevant for students, remote workers, and people who perform tasks that require long periods of concentration. A real-time focus awareness tool could help users structure breaks, improve productivity and better understand their own attention patterns over time.

From a technical perspective, the project demonstrates how brain-computer interface data can be processed and transformed into understandable user feedback. The system classifies the user state as `FOCUSED` or `DRIFTING` and provides feedback through audio cues and an overlay state file.

At the same time, the project raises important ethical considerations. EEG data is sensitive personal data, so privacy and data security must be handled carefully. The system should not be used to monitor or judge people without their consent. Additionally, the classification is experimental and should not be interpreted as a medical or diagnostic result. The main purpose of this prototype is to explore real-time neurofeedback for focus awareness in a responsible and transparent way.


## Solution Design

Our solution is designed as a real-time EEG-based focus awareness system. The system receives EEG brain signal data, processes the signal, extracts relevant frequency-band features, and classifies the user’s current cognitive state. The result is then translated into simple feedback states: `FOCUSED` or `DRIFTING`.

The project supports two different data input modes. In offline mode, EEG data is replayed from a CSV file, which makes it possible to test and debug the system without a connected device. In live mode, the system connects to an IDUN Guardian EEG device and processes incoming raw EEG data in real time.

The technical pipeline starts with buffering the incoming EEG samples. The raw signal is then filtered using a notch filter to reduce power-line noise and a bandpass filter to keep the relevant EEG frequency range. After filtering, the system calculates the power spectral density using Welch’s method. Based on this spectrum, the power of different EEG frequency bands such as theta, alpha, and beta is extracted.

During the first calibration phase, the system collects baseline information from the user’s EEG signal. This baseline is used to make the later classification more stable and personalized. After calibration, the system calculates two main indicators: an engagement score and a relaxation score. A higher engagement score is interpreted as a more focused state, while a higher relaxation or drifting-related score can indicate that the user’s attention is decreasing.

To avoid unstable or rapidly changing results, the system applies smoothing and a minimum dwell time before confirming a new state. This makes the feedback more reliable and prevents the system from switching too quickly between `FOCUSED` and `DRIFTING`.

The final state is communicated to the user in two ways. First, the system can play different audio cues when the user changes state. Second, the current state is written to a shared text file called `lofilia_state.txt`, which will be used by an external overlay script.

Overall, the solution combines signal processing, real-time classification, and user feedback into one prototype. The design focuses on feasibility and modularity, allowing the system to be tested with recorded EEG data and later extended to live neurofeedback applications.


## Architecture
