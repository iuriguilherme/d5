/taches-cc-resources:create-prompt

Create a prompt which will call the /ce:brainstorm command to perfom a brainstorm for this application.

## Scope

This is gonna be an organizer application which will organize general subjects as ideas for posting in social media.

## User stories

The user will be able to input general subjects as ideas;

The user will be able to ask for a suggestion of one the subjects for posting in social media;

The user will be able to input what they posted on social media as a feedback to document the final result;

The user will be able to add their posting history of social media websites so the system can work on prediction of subjects;

## Cron system

The system will remind the user in a fixed or dynamic schedule that it is time to post;

The user will be able to set frequency of reminders (for example twice per week, once per day, etc.);

When it's time to remind the user that a post is due, the system will select one subject according to the configured heuristics;

## Persistence

All input of the user will be stored as plain text and in a vector database and analyzed with historical data of posts;

## Analytics

The heuristics for suggestions will be based on social media best practices such as avoiding the same subject too often;

The default and simples heuristics can be a random choice from the subjects pool;

The default frequency for scheduled reminders can be whatever are the best practices for each website (instagram, tiktok, threads, etc.);

The user should be able to suggest their own social media strategy and feed the algorithm ith their own research for added weight in the decision matrix;

If the user adds their posting history of the social media websites, there must be a system in place to predict and suggest new subjects. The suggestions must be approved by the user; 

## Tech stack

The user interface is a Telegram bot. The maintainer only has experience with Python and Aiogram but other telegram bot frameworks may be suggested instead, even with other programming languages. Before suggesting, a deep research should be performed;

We need two databases: one to store plain text for the user input and one vector database for analytics;
