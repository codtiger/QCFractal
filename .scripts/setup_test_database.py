from collections import OrderedDict
import glob
import sys
import json
import os

import mongo_qcdb as mdb

#mongo = mongo_helper("192.168.2.139", 27017, "local")
mongo = mdb.mongo_helper.MongoSocket("127.0.0.1", 27017, "local")
for db_name in mongo.client.database_names():
    mongo.client.drop_database(db_name)

collections = ["molecules", "databases", "pages"]

# Define the descriptor field for each collection. Used for logging.
descriptor = {"molecules": "name", "databases": "name", "pages": "modelchem"}

# Add all JSON
for col in collections:
    prefix = os.path.dirname(os.path.abspath(__file__)) + "/../databases/DB_HBC6/" + col + "/"
    for filename in glob.glob(prefix + "*.json"):
        json_data = open(filename).read()
        # Load JSON from file into OrderedDict
        data = json.loads(json_data, object_pairs_hook=OrderedDict)
        if (col == "molecules"):
                inserted = mongo.add_molecule(data)
        if (col == "databases"):
                inserted = mongo.add_database(data)
        if (col == "pages"):
                inserted = mongo.add_page(data)
#        print("[" + col + "] Added " + data[descriptor[col]] + " to " + col + ". Success=" + str(inserted) + ".")
