# Personal Assistant App Specifications


## Goals
- This application is meant to be a personal assistant agent that keeps me focused on the most important tasks throughout my day. 
- It should also make recommendations about how I can become more productive based on my schedule
- In order for it to be fully effective the personal assistant should be able to think and act on it's own, but it should also take orders from me when prompted

## Must Have Functionality
- Ability to track tasks and prioritize whats important now vs later
- Monitor multiple sources for key information I should know about including my email, calendar, slack, and meeting notes
- Automatically create tasks when appropriate from my emails, slack messages, and meeting notes
- Notify me of important documents I should read and provide comments on in my company's google drive
- Suggest calendar optimizations throughout my week, helping me prioritze what is most important and delaying meetings that are not critical
- Help me schedule meetings based on my availability as well as the other meeting attendees availability

## User Experience
- This application can run as a local application that is started on the command line
- The main interface for interacting with the critical information and tasks can just be a local document
- There should be a way to remind me to review the document on a regular basis
- Configurations for the personal assistant agent shoudl be stored in a simple yaml config file

## Future Considerations
- Using Obsidian vault as the document store
- Creating a user interface to interact with the personal assistant agent configuration
- Ability to view detailed logs of the agent
