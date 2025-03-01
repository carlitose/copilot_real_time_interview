# Interview Assistant

A job interview assistant for software developers that uses OpenAI's GPT-4o Audio.

## Description

Interview Assistant is a desktop application that helps software developers during technical job interviews. The application records the interview audio, transcribes it using GPT-4o Audio, detects technical questions, and generates detailed responses using GPT-4o.

Responses are displayed both in the main interface and in easily accessible popups during the interview.

## Main Features

- **Real-Time Audio Transcription**: Records and transcribes audio during interviews.
- **Automatic Question Detection**: Automatically detects when a question is asked.
- **Detailed Technical Responses**: Generates technical responses using GPT-4o.
- **Response Popups**: Displays responses in popups for easy reference during the interview.
- **Screenshot Functionality**: Allows capturing, saving, and sharing interview screens.
- **Conversation Saving**: Saves the entire conversation in JSON format.

## Requirements

- Python 3.8 or higher
- OpenAI API key (to use GPT-4o)
- Dependencies listed in `requirements.txt`

## Installation

1. Clone the repository or download the files:
   ```
   git clone https://github.com/tuo-username/interview-assistant.git
   cd interview-assistant
   ```

2. Install dependencies:
   ```
   pip install -r interview_assistant/requirements.txt
   ```

3. Create a `.env` file in the `interview_assistant` directory based on the `.env.example` file:
   ```
   cp interview_assistant/.env.example interview_assistant/.env
   ```

4. Edit the `.env` file and add your OpenAI API key:
   ```
   OPENAI_API_KEY=your-openai-api-key-here
   ```

## Usage

You can start the application in one of the following ways:

1. By running the main script:
   ```
   python run.py
   ```

2. By running the launcher from inside the interview_assistant directory:
   ```
   cd interview_assistant
   python launcher.py
   ```

## User Guide

1. Press the "Start Recording" button to begin recording audio.
2. Speak clearly, asking technical questions related to software development.
3. The application will automatically detect questions and generate responses.
4. Responses will appear in the "Response" area and in a popup.
5. Use the "Screenshot" button to capture the screen during the interview.
6. The "Share Screenshot" button allows you to save and copy the image path.
7. At the end of the interview, use "Save Conversation" to save the conversation in JSON format.

## Project Structure

```
interview_assistant/
├── __init__.py
├── main.py           # Main application
├── launcher.py       # Startup script
├── requirements.txt  # Dependencies
├── setup.py          # Installation script
├── .env.example      # Configuration example
├── README.md         # Documentation
└── utils/            # Utility modules
    ├── __init__.py
    ├── question_detector.py  # Question detector
    └── screenshot_utils.py   # Screenshot utilities
```

## License

MIT

## Acknowledgements

This project is based on:
- OpenAI GPT-4o for response generation
- OpenAI Whisper for audio transcription
- PyQt5 for the graphical interface
