/taches-cc-resources:create-prompt

Create a prompt which will call the /ce:brainstorm command to perfom a brainstorm for this application.

## Scope

This is gonna be an organizer application which will organize general subjects as ideas for posting in social media.

## User stories

The user will be able to input general subjects as ideas;

The user will be able to ask for a suggestion of one the subjects for posting in social media;

The user will be able to input what they posted on social media;

## Persistence

All input of the user will be stored as plain text and in a vector database and analyzed with past posted material;

## Analytics

The heuristics for suggestions will be based on social media best practices such as avoiding the same subject too often;

The user should be able to suggest their own social media strategy for added weight on the decision matrix;

## Tech stack

The user interface is a Telegram bot. The maintainer only has experience with Python and Aiogram but other telegram bot frameworks may be suggested instead, even with other programming languages. Before suggesting, a deep research should be performed.

We need two databases: one to store plain text for the user input and one vector database for analytics.
