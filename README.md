# Odin Config

# To set up MongoDB for the application

First, to use MongoDB, you will need to install it (https://www.mongodb.com/docs/manual/installation/).  
These steps may automatically install Compass (see below). (Atlas is not recommended as this may behave differently to a local installation.)  
From there, you will have a connection string to connect to the database.  
The default is the local database string (mongodb://localhost:27017).
Atlas has its own connection requirements: https://www.mongodb.com/docs/guides/atlas/connection-string/#what-you-ll-need

Now you create a database and collections within it (we will need two: for the instrument config, and the history).  
How you create these will depend on the method used.

1. MongoDBCompass is a graphical user interface (GUI) for you to use and is very straightforward to use.  
Connect, create a database and collection in it in the left tab, and then click 'add data' to add the data in your preferred format (list, json or table).  
Mongosh (below) is included with this and can be used instead of the graphical interface.  

2. Mongosh (mongo shell) is a command-line interface which can interact in the same ways through use of commands.  
To run independently of Compass it needs to be installed separately [1].  
Run the .exe file to launch it, or add the .exe's directory to your (system environment variables) Path to access this from any terminal.  
After connecting [2], create a database (`use <database>`) and insert some data into the collection, which will automatically make both the db and the collection. (`use instrument` // `db.collectionName.insertOne(...)`) [3].  
[1] https://www.mongodb.com/docs/mongodb-shell/install/  
[2] https://www.mongodb.com/docs/mongodb-shell/connect/#std-label-mdb-shell-connect  
[3] https://www.mongodb.com/docs/mongodb-shell/crud/insert/#std-label-mongosh-insert  

At the bottom of this README you can find the commands for mongosh, in order, to insert six dummy configurations (2 of layers 0, 1, 2) for the purposes of demonstration into a database called 'tormongo' and a collection called 'Instrument'.  
These can serve as a reference for the grammar required by Mongo for this sort of data entry.  
The configurations demonstrate the ability of the config manager to edit, add to, or overwrite parameters without affecting any others (see 'subtree' within).

From there, it is just a case of creating and inserting the data, which may take some time (but hopefully no more time than creating the parameter files individually).
The configuration options all need these attributes:

**meta/**: the **layer** and the **revision** (initially zero!) are mandatory. optionally: a **facility**, **date** and **author**.  
**Name**: the name of the option. The capitalisation of 'Name' (the key) is important.

**parents**: an array of higher-level configuration options that the current option can be applied to.  
**children**: an array of lower-level configuration options that the current option can have applied to it.  
(any option with another option as its parent will be a child to that option).  
    Use the example data to see how these interact.  
**parameters**: a 'dictionary' of parameters. This can contain whatever parameters that option needs, including nested dictionaries, arrays, integers, etc.. This is the actual configuration to be applied.

After this, an \_id attribute is automatically generated and cannot be edited.

# To run the application

- Have set up odin-control through `git clone https://github.com/odin-detector/odin-control.git` and running `python setup.py develop` 

- Clone this repository adjacent to odin-control.  
- Run `python setup.py develop` from the python directory in odin-config in your terminal.
- Adjust any of the needed configuration settings in `python/test/config/config_manager.cfg`.
    This might include adapter references (for the instrument) and db/collection names.
- Run the app with `odin_server --config test/config/config_manager.cfg` (assuming from the `python/` directory but this is not important).  
- Navigate to localhost:8888 to access the config manager and whatever instrument is running alongside it in your adapter.

### in python/manager/

`config_manager.py` deals with the accessing and processing of the data.
Changes to how data is read from or written to the databases is done here, along with the ancestry aggregation and valid options processing.  
Also included is the managing of adapter registry and callbacks for instrument adapters to use to get the complete configurations.  
`config_manager_adapter.py` initialises the config_manager and reads in the settings for it, while handling the API requests.  
Default settings are defined here, and the settings are then passed to config_manager.
The options read in are provided in `test/config/config_manager.cfg`.  
`instrument_adapter.py` is a dummy adapter reading in some information from the demonstration data. It demonstrates registering a
callback with the config manager to request or be sent information from it.

### in test/

In `config/` is the config file which contains the default options for db names and connection strings.  
In `static/js` is javascript to interact with each adapter.  
`static/index.html` creates a page with two tabs: one for the config manager and another simple page to display values from the instrument adapter's parameter tree and allow the instrument adapter to fetch any completed configuration from the config manager.


# Example mongosh commands

To connect to a mongo instance, create a database called tormongo, and insert some dummy data.

`mongosh "<connectionString>"`  
`use tormongo`  
```
db.Instrument.insertMany(
    [{
        "Name": "UserOperation",
        "meta": {
            "layer": 0,
            "revision": 0,
            "facility": "",
            "author": "",
            "date": "",
        },
        "parents": [],
        "children": ["LowPowerMode", "LowSpeedMode"],
        parameters: {
            "subtree": {
                "specific_num": 5,
                "random_num": 42,
                "curious_num": 3.14
            },
            "sweep": "false",
            "power": 100,
            "tick_rate": 10000,
            "operation": "alpha"
        }
    },
    {
        "Name": "CalibrationTest",
        "meta": {
            "layer": 0,
            "revision": 0,
            "facility": "",
            "author": "",
            "date": "",
        },
        "parents": [],
        "children": ["LowSpeedMode"],
        parameters: {
            "subtree": {
                "specific_num": 6,
                "random_num": 2001,
                "curious_num": 6.28
            },
            "sweep": "false",
            "power": 100,
            "tick_rate": 10000,
            "operation": "beta"
        }
    },
    {
        "Name": "LowPowerMode",
        "meta": {
            "layer": 1,
            "revision": 0,
            "facility": "",
            "author": "",
            "date": "",
        },
        "parents": ["UserOperation"],
        "children": ["Debug1"],
        parameters: {
            "subtree": {
                "curious_num": 2.72828
            },
            "power": 30
        }
    },
    {
        "Name": "LowSpeedMode",
        "meta": {
            "layer": 1,
            "revision": 0,
            "facility": "",
            "author": "",
            "date": "",
        },
        "parents": ["UserOperation", "CalibrationTest"],
        "children": ["VrefSweep", "Debug1"],
        parameters: {
            "subtree": {
                "specific_num": 10
            },
            "tick_rate": 5000,
            "that's": "numberwang!"
        }
    },
    {
        "Name": "Debug1",
        "meta": {
            "layer": 2,
            "revision": 0,
            "facility": "",
            "author": "",
            "date": "",
        },
        "parents": ["LowPowerMode", "LowSpeedMode"],
        "children": [],
        parameters: {
            "subtree": {
                "angry_num": 13
            },
            "operation": "debug"
        }
    },
    {
        "Name": "VrefSweep",
        "meta": {
            "layer": 2,
            "revision": 0,
            "facility": "",
            "author": "",
            "date": "",
        },
        "parents": ["LowSpeedMode"],
        "children": [],
        parameters: {
            "subtree": {
                "random_num": 9001
            },
            "sweep": "true"
        }
    }]
);
