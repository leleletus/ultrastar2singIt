import json
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

# Known manual mappings for songs that iTunes fails to find or blocks
HARDCODED_MAPPING = {
    'PrincesOfTheUniverse': ('Queen', 'Princes Of The Universe'),
    'Rise': ('Jonas Blue', 'Rise (feat. Jack & Jack)'),
    'RoadLessTraveled': ('Lauren Alaina', 'Road Less Traveled'),
    'Royals': ('Lorde', 'Royals'),
    'SayYouWontLetGo': ('James Arthur', "Say You Won't Let Go"),
    'SinglesYouUp': ('Jordan Davis', 'Singles You Up'),
    'SmallTownBoy': ('Dustin Lynch', 'Small Town Boy'),
    'SoAmI': ('Ava Max', 'So Am I'),
    'SomeSay': ('Nea', 'Some Say'),
    'SomebodyThatIUsedToKnow': ('Gotye', 'Somebody That I Used To Know (feat. Kimbra)'),
    'SomebodyToLove': ('Queen', 'Somebody To Love'),
    'SomewhereIBelong': ('Linkin Park', 'Somewhere I Belong'),
    'Speechless': ('Robin Schulz', 'Speechless (feat. Erika Sirola)'),
    'Stitches': ('Shawn Mendes', 'Stitches'),
    'StoleTheShow': ('Kygo', 'Stole The Show (feat. Parson James)'),
    'StreetsOfBakersfield': ('Dwight Yoakam', 'Streets of Bakersfield'),
    'StrongerWhatDoesntKillYou': ('Kelly Clarkson', "Stronger (What Doesn't Kill You)"),
    'StupidLove': ('Lady Gaga', 'Stupid Love'),
    'Sucker': ('Jonas Brothers', 'Sucker'),
    'SunnyAnd75': ('Joe Nichols', 'Sunny and 75'),
    'SweetButPsycho': ('Ava Max', 'Sweet But Psycho'),
    'Symphony': ('Clean Bandit', 'Symphony (feat. Zara Larsson)'),
    'TakeYourTime': ('Sam Hunt', 'Take Your Time'),
    'ThankUNext': ('Ariana Grande', 'thank u, next'),
    'ThatsWhatILike': ('Bruno Mars', "That's What I Like"),
    'TheChair': ('George Strait', 'The Chair'),
    'TheGambler': ('Kenny Rogers', 'The Gambler'),
    'TheInvisibleMan': ('Queen', 'The Invisible Man'),
    'TheMiddle': ('Zedd, Maren Morris & Grey', 'The Middle'),
    'TheShowMustGoOn': ('Queen', 'The Show Must Go On'),
    'TheSign': ('Ace of Base', 'The Sign'),
    'TheresNothingHoldinMeBack': ('Shawn Mendes', "There's Nothing Holdin' Me Back"),
    'TheseDays': ('Rudimental', 'These Days (feat. Jess Glynne, Macklemore & Dan Caplen)'),
    'ThinkALittleLess': ('Michael Ray', 'Think a Little Less'),
    'ThisGirl': ("Kungs vs Cookin' on 3 Burners", 'This Girl'),
    'ThisLove': ('Maroon 5', 'This Love'),
    'Thunder': ('Imagine Dragons', 'Thunder'),
    'Thunderclouds': ('LSD', 'Thunderclouds (feat. Sia, Diplo & Labrinth)'),
    'TieYourMotherDown': ('Queen', 'Tie Your Mother Down'),
    'TooGoodAtGoodbyes': ('Sam Smith', 'Too Good At Goodbyes'),
    'Trampoline': ('SHAED', 'Trampoline'),
    'Trumpets': ('Jason Derulo', 'Trumpets'),
    'UnderPressure': ('Queen & David Bowie', 'Under Pressure'),
    'Wannabe': ('Spice Girls', 'Wannabe'),
    'WayDownWeGo': ('Kaleo', 'Way Down We Go'),
    'WeAreTheChampions': ('Queen', 'We Are The Champions'),
    'Wellerman': ('Nathan Evans', 'Wellerman (Sea Shanty)'),
    'WhatsUp': ('4 Non Blondes', "What's Up?"),
    'WhenYoureGone': ('Avril Lavigne', "When You're Gone"),
    'WhereAreYouNow': ('Lost Frequencies & Calum Scott', 'Where Are You Now'),
    'WhoWantsToLiveForever': ('Queen', 'Who Wants To Live Forever'),
    'WithoutYou': ('The Kid LAROI', 'WITHOUT YOU'),
    'Wolves': ('Selena Gomez & Marshmello', 'Wolves'),
    'X': ('Nicky Jam x J. Balvin', 'X'),
    'YouBrokeMeFirst': ('Tate McRae', 'you broke me first'),
    'YouDontKnowMe': ('Jax Jones', "You Don't Know Me (feat. RAYE)"),
    'YouGiveLoveABadName': ('Bon Jovi', 'You Give Love A Bad Name'),
    'YouKeepMeHanginOn': ('Kim Wilde', "You Keep Me Hangin' On"),
    'YouLetMeWalkAlone': ('Michael Schulte', 'You Let Me Walk Alone'),
    'YouShouldBeHere': ('Cole Swindell', 'You Should Be Here'),
    'YouSpinMeRound': ('Dead Or Alive', 'You Spin Me Round (Like a Record)'),
    'YourPower': ('Billie Eilish', 'Your Power'),
    'YourSong': ('Rita Ora', 'Your Song'),
    'YoureMyBestFriend': ('Queen', "You're My Best Friend"),
    'Yummy': ('Justin Bieber', 'Yummy')
}

def split_camel_case(s):
    import re
    return re.sub('([a-z0-9])([A-Z])', r'\1 \2', s)

def fetch_itunes_metadata(song_id):
    if song_id in HARDCODED_MAPPING:
        return song_id, HARDCODED_MAPPING[song_id][0], HARDCODED_MAPPING[song_id][1]

    query = split_camel_case(song_id)
    url = f"https://itunes.apple.com/search?term={urllib.parse.quote(query)}&entity=song&limit=1"
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read())
            if data['resultCount'] > 0:
                track = data['results'][0]
                return song_id, track.get('artistName', 'Unknown Artist'), track.get('trackName', 'Unknown')
    except Exception as e:
        pass
    
    return song_id, None, None

def main(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    songs = data.get('songs', [])
    to_fix = [s for s in songs if s.get('artist') in ['Unknown Artist', 'Unknown']]
    
    print(f"Found {len(to_fix)} songs with Unknown Artist.")
    if not to_fix:
        return
        
    fixed_count = 0
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_itunes_metadata, s['id']): s for s in to_fix}
        for future in futures:
            s = futures[future]
            song_id, artist, title = future.result()
            if artist and title and artist != 'Unknown Artist':
                s['artist'] = artist
                s['title'] = title
                fixed_count += 1
                print(f"Fixed: {song_id} -> {artist} - {title}")

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    print(f"\nSuccessfully fixed {fixed_count} songs.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 fix_dlc_artists_metadata.py <path_to_json>")
    else:
        main(sys.argv[1])
