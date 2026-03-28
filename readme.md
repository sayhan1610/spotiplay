# Spotify Playlists Showcase

## Project Description

This project is a web application developed for CIS 115. It displays a curated collection of public Spotify playlists using the Flask framework and the Spotify Web API. The application fetches playlist metadata and presents it in a user-friendly interface.

## Features

- Displays public Spotify playlists with metadata including name, description, cover art, and track count.
- Utilizes Spotify's client credentials flow for secure API access.
- Provides a simple web interface with styled playlist cards.
- Includes an optional JSON API endpoint.

## Technologies Used

- Python
- Flask
- Spotify Web API
- HTML, CSS, JavaScript

## Installation and Setup

1. Ensure Python is installed on your system.

2. Clone the repository or download the project files.

3. Create a virtual environment:
   ```
   python -m venv venv
   venv\Scripts\activate  # On Windows
   ```

4. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

5. Create a `.env` file in the project root with the following content:
   ```
   CLIENT_ID=your_spotify_client_id
   CLIENT_SECRET=your_spotify_client_secret
   FLASK_APP=app.py
   FLASK_ENV=development
   ```

6. Obtain Spotify API credentials from the Spotify Developer Dashboard.

7. Create a `playlists.json` file with the desired playlist URLs or IDs, for example:
   ```json
   [
     "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
     "https://open.spotify.com/playlist/37i9dQZF1DX0XUsuxWHRQd"
   ]
   ```

## Usage

Run the application using the following command:
```
python app.py
```

Access the application in a web browser at `http://localhost:5000`.

## Course Information

This project was created as part of CIS 115 coursework.

# Open in your browser:

```
http://127.0.0.1:5000
```

## Suggested Project Structure

```text
spotiplay/
├── app.py
├── requirements.txt
├── README.md
├── playlists.json
├── .env
├── templates/
│   ├── index.html
│   └── playlist.html
└── static/
    ├── css/
    │   └── styles.css
    └── js/
        └── main.js
```

## Planned Routes

* `GET /` - Main page showing all playlists
* `GET /api/playlists` - JSON output of playlists
* `GET /playlist/<playlist_id>` - Detailed playlist view

## Notes

* Only public playlists are displayed.
* Spotify secrets should never be exposed in frontend code.
* The app can be extended later with playlist detail pages, filters, and animations.
* Curating playlists manually ensures reliability and simplicity.

## Future Improvements

* Playlist detail pages with track listings
* Theme cards based on playlist cover colors
* Search and filter playlists
* Smooth loading states and transitions
* Mobile responsiveness
* Tag-based categorization like `chill`, `coding`, `gym`, or `night drive`

