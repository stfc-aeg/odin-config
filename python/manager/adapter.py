"""Demo adapter for ODIN config manager

This class implements the basic functionality needed for the config manager

Mika Shearwood, STFC Detector Systems Software Group
"""
import logging
import tornado
import time
import sys
from concurrent import futures

from tornado.ioloop import IOLoop, PeriodicCallback
from tornado.concurrent import run_on_executor
from tornado.escape import json_decode

from odin.adapters.adapter import ApiAdapter, ApiAdapterResponse, request_types, response_types
from odin.adapters.parameter_tree import ParameterTree, ParameterTreeError
from odin._version import get_versions

import pymongo
from pymongo import MongoClient
from collections import Counter

from pprint import pprint

class ManagerAdapter(ApiAdapter):
    """System info adapter class for the ODIN server.

    This adapter provides ODIN clients with information about the server and the system that it is
    running on.
    """

    def __init__(self, **kwargs):
        """Initialize the ManagerAdapter object.

        This constructor initializes the ManagerAdapter object.

        :param kwargs: keyword arguments specifying options
        """
        # Intialise superclass
        super(ManagerAdapter, self).__init__(**kwargs)

        self.manager = Manager()

        logging.debug('ManagerAdapter loaded')

    @response_types('application/json', default='application/json')
    def get(self, path, request):
        """Handle an HTTP GET request.

        This method handles an HTTP GET request, returning a JSON response.

        :param path: URI path of request
        :param request: HTTP request object
        :return: an ApiAdapterResponse object containing the appropriate response
        """
        try:
            response = self.manager.get(path)
            status_code = 200
        except ParameterTreeError as e:
            response = {'error': str(e)}
            status_code = 400

        content_type = 'application/json'

        return ApiAdapterResponse(response, content_type=content_type,
                                  status_code=status_code)
    
    @request_types('application/json')
    @response_types('application/json', default='application/json')
    def post(self, path, request):
        """Handle an HTTP POST request.
        
        This method handles an HTTP POST request, returning a JSON response.
        
        :param path: URI path of request.
        :param request: HTTP request object
        :return: an ApiAdapterResponse object containing the appropriate response.
        """

        content_type = 'application/json'
        try:
            data = json_decode(request.body)
            self.manager.post(path, data)
            response = self.manager.get(path)
            status_code = 200
        except ManagerError as e:
            response = {'error': str(e)}
            status_code = 400
        except (TypeError, ValueError) as e:
            response = {'error': 'Failed to decode POST request body: {}'.format(str(e))}
            status_code = 400

        # logging.debug(response)

        return ApiAdapterResponse(response, content_type=content_type, status_code=status_code)

    @request_types('application/json')
    @response_types('application/json', default='application/json')
    def put(self, path, request):
        """Handle an HTTP PUT request.

        This method handles an HTTP PUT request, returning a JSON response.

        :param path: URI path of request
        :param request: HTTP request object
        :return: an ApiAdapterResponse object containing the appropriate response
        """

        content_type = 'application/json'

        try:
            data = json_decode(request.body)
            self.manager.set(path, data)
            response = self.manager.get(path)
            status_code = 200
        except ManagerError as e:
            response = {'error': str(e)}
            status_code = 400
        except (TypeError, ValueError) as e:
            response = {'error': 'Failed to decode PUT request body: {}'.format(str(e))}
            status_code = 400

        logging.debug(response)

        return ApiAdapterResponse(response, content_type=content_type,
                                  status_code=status_code)

    def delete(self, path, request):
        """Handle an HTTP DELETE request.

        This method handles an HTTP DELETE request, returning a JSON response.

        :param path: URI path of request
        :param request: HTTP request object
        :return: an ApiAdapterResponse object containing the appropriate response
        """
        response = 'ManagerAdapter: DELETE on path {}'.format(path)
        status_code = 200

        logging.debug(response)

        return ApiAdapterResponse(response, status_code=status_code)

    def cleanup(self):
        """Clean up adapter state at shutdown.

        This method cleans up the adapter state when called by the server at e.g. shutdown.
        It simplied calls the cleanup function of the manager instance.
        """
        self.manager.cleanup()

class ManagerError(Exception):
    """Simple exception class to wrap lower-level exceptions."""

    pass


class Manager():
    """Manager - class that reads MongoDB collections to store and handle information about
    configuration options.
    """

    def __init__(self, instrument="Instrument"):
        """Initialise the Manager object.

        This makes relevant database connections, accesses collections and builds mutable parameter trees.
        """
        # Initialise DB client and vars
        self.client = MongoClient("mongodb://localhost:27017")
        self.db = self.client.tormongo
        self.instrument = instrument  # collection name for instrument
        self.all_configs, self.all_names, self.named_config, self.layered_config, self.ancestry = self.get_database_entries(self.instrument)

        history_db = instrument + "History"
        self.instrumentHistory = self.db[history_db]  # collection name for instrument revisions
        # self.revision = self.get_all_revisions(self.instrumentHistory)

        # Store initialisation time
        self.init_time = time.time()

        # Get package version information
        version_info = get_versions()

        # Parameter tree for database
        self.param_selection_names = []
        self.param_selection = []
        # self.valid_options = [config["Name"] for config in self.all_configs]
        self.valid_options = {
            layer: [value["Name"] for value in values] for layer, values in self.layered_config.items()
        }
        self.used_layers = []

        db_tree = ParameterTree({
            'config_num': (lambda: len(self.all_configs), None),
            'layer_num': (lambda: len(self.layered_config), None),
            'param_selection_names': (lambda: self.param_selection_names, self.set_param_selection),
            'valid_options': (lambda: self.valid_options, self.set_valid_options),  # All are valid
            'current_merge': (lambda: self.get_current_merge(), None)
        })

        # Making a parameter tree of the configs. Need a get for the value otherwise it won't work
        # This contains the whole entry stored under the name. Easiest way to store.
        # Unique names should be enforced in code. Relationships/aggregation/versioning need them
        #       > especially versioning, which cannot use _id since _id must be unique
        #       > and versioning necessarily uses duplicates if versioned more than once 
        config_tree_dict = {}
        change_tree_dict = {}

        for entry in self.all_configs:
            config_tree_dict[entry["Name"]] = (self.get_named_config(entry["Name"]), self.set_config)
            change_tree_dict[entry["Name"]] = (self.get_config_revisions(entry["Name"]), None)
      
        config_tree = ParameterTree(config_tree_dict, mutable=True)
        change_tree = ParameterTree(change_tree_dict, mutable=True)
        # Considerations on how to handle the change tree.
        # Depends on when the revisions are actually made and saved.
        # Should it just require a restart? That feels awkward. But what would the alternative be?
        # Trigger: when a user commits their changes.
        # Outcome: all_configs tree is updated already, so config_revisions needs the latest version
        # and you save the latest version (all_configs) to the db and increment the revision.
        # This means that you need something to track which have been edited so far. UI-side can do
        # that. Then, you need a check for things that have been edited back to original (comparison on
        # update). Then you make the save, increment revision and get that latest one into config_revisions
        # which i actually think is done automatically with the getter? 
        # TL;DR: commit, check all edited for changes, increment and save, update config_revisions.

        # Store all information in a parameter tree
        self.param_tree = ParameterTree({
            'odin_version': version_info['version'],
            'tornado_version': tornado.version,
            'db_collection': (lambda: self.instrument, None),
            'server_uptime': (self.get_server_uptime, None),
            'all_configs': config_tree,
            'config_revisions': change_tree,
            'selection': db_tree,
            'all_names': (self.all_names, None)
        }, mutable=True)

    def get_database_entries(self, db_name):
        """Get the data from mongo with the db specified in __init__.
        In this case it's going to be 'Instrument' in 'tormongo'.
        """
        Instrument = self.db[db_name]
        pipeline = [  # Array of aggregation steps
            {"$graphLookup": {"from": "Instrument","startWith": "$children", "connectFromField": "children","connectToField": "Name","as": "descendants"}},
            {"$graphLookup": {"from": 'Instrument',"startWith": '$parents',"connectFromField": 'parents',"connectToField": "Name","as": 'ancestors'}},
            {"$sort": {"layer": pymongo.ASCENDING}}
        ]
        results = Instrument.aggregate(pipeline)  # All configs with full family history
        all = []  # All configs in original form
        named = {}  #  key:value, name:object
        layered = {}  # key:list, layer:(list of configs in layer)
        all_names = {}  # just the names of all the configs against layers. static.

        for result in results:
            all.append(result)
            # result.pop("ancestors")
            # result.pop("descendants")  # don't want this in all the results

            named[result["Name"]] = result  # Dict sorted by name

            if result["meta"]["layer"] not in layered.keys():  # Check if layer exists
                layered[result["meta"]["layer"]] = []  # Create layer if it does not
                all_names[result["meta"]["layer"]] = []
            layered[result["meta"]["layer"]].append(result)
            all_names[result["meta"]["layer"]].append(result["Name"])
        # Necessary to layer the 'all_names' for the UI to access on initialisation.

        ancestry = {}
        for config in all:
            ancestry[config["Name"]] = {
                "ancestors": config["ancestors"],
                "descendants": config["descendants"]
            }
            config.pop("ancestors")
            config.pop("descendants")
            # We have these in ancestry now and they are huge

        return all, all_names, named, layered, ancestry

    def get_config_revisions(self, name):
        """Get all the revisions for a given config option.

        :param name: name of the config option to search for
        """
        # So you need to access this via a request to the tree
        # To get the latest version of a specific config option
        # So, what do you query?
        # You need to make a GET request, where this thing will make a transaction to get the info
        # I guess you just have it be its own branch of the tree and then you never request the entire thing to avoid that tremendous inefficiency
        results = self.instrumentHistory.find( {"Name": { "$eq": name }} )
        revisions = []
        for result in results:
            revisions.append(result)

        return revisions
    
    def get_named_config(self, name):
        """Return the details of a given config."""
        return self.named_config[name]
    
    def set_config(self, request):
        """Set the specified config value to the replacement.
        Assumes that the access is done through all_configs/config_name.
        """
        # I expect this would be done in one go, show the user a JSON file they can edit, essentially
        # so you would just direct them to all_configs/confName and then replace the whole thing.
        # This currently assumes you go directly to e.g.: curlMode 

        node = self.latest_path.split("/")[-2]  # self.path ends with /

        for key, item in request.items():
            self.named_config[node][key] = item
            # self.named_config["curlMode"]["parameters"] = request

    def set_param_selection(self, names):
        """Set the current selection of parameters to dictate remaining valid options.
        This process currently assumes that multiple can be entered at once instead of separately,
        and so will be massively simplified once this is true.
        (Checks would not be required as only valid combinations could be selected).
        # self.param_selection.append(self.named_config[name]) // self.param_selection_names.append(name) // set_valid_options()

        Ideally, one name would be provided at a time, and added to the existing selection.
        This could be handled on the controller side (submitting a request with all the selections
        whenever one is made).
        """
        self.param_selection_names = []  # These lines also go once parameters are selected one at a time
        self.param_selection = []

        # checks
        if len(names) == 0:
            self.valid_options = {   # reset
                layer: [value["Name"] for value in values] for layer, values in self.layered_config.items()
            }  # really i should have a 'reset_valid_options()' somewhere..
  
        layerCheck = [self.named_config[name]["meta"]["layer"] for name in names]
        if (len(names) > len(self.layered_config)) or (len(layerCheck) != len(set(layerCheck))):
            # More names than layers, or more than one item from any layer
            print("select only one option from each layer")
            return  # do nothing

        for i in range(len(names)):
            self.param_selection_names.append(names[i])
            self.param_selection.append(self.named_config[names[i]])
            length = self.set_valid_options()

            if (length == 0) and (i < len(self.layered_config)):
                # if no valid options and not reached one choice per layer, invalid selection
                print("these options are not compatible, try again")
                self.param_selection_names = []
                self.param_selection = []
                self.valid_options = {   # reset
                    layer: [value["Name"] for value in values] for layer, values in self.layered_config.items()
                }
                return
            else:
                pass

    def set_valid_options(self):
        """Determine the remaining valid options.
        This iterates over the list of selections (however that is decided) and finds options that
        are valid relatives of all of the selections.
        """
        self.used_layers = []
        self.used_layers.append(selection["meta"]["layer"] for selection in self.param_selection)
        allOptions = []

        for selection in self.param_selection:

            # ancestry[selection name][ancestors]
            for ancestor in self.ancestry[selection["Name"]]["ancestors"]:
                if ancestor["meta"]["layer"] not in self.used_layers:
                    allOptions.append(ancestor)

            for descendant in self.ancestry[selection["Name"]]["descendants"]:
                if descendant["meta"]["layer"] not in self.used_layers:
                    allOptions.append(descendant)

        # Unpack options
        validNameList = [item["Name"] for item in allOptions]
        validCounter = Counter(validNameList)  # Count names

        allOptions = [  # Take all the names that appear in EVERY selection's family tree
            record for record, count in validCounter.items() if count == len(self.param_selection)
        ]
        # Could likely do this in one step but it would be very hard to read.
        self.valid_options = {
            layer: [value["Name"] for value in values if value["Name"] in allOptions] for layer, values in self.layered_config.items()
        }  # For every layer, look at its list of values. Put a str as the key and list all of the values in that list that appear in all the valid options
        
        return len(self.valid_options)

    def get_current_merge(self):
        """Function to continuously merge the current selection of options.
        If there is one selection, this is just that parameter's options (merged against nothing).
        The merge will be re-done each time an option is added. This is because the order of merge
        is important so as to always overwrite the 'left-most' option.
        """

        if len(self.param_selection_names) == 0:
            return "Select an option to merge"  # If nothing has been selected, leave it blank
        
        layeredParamsToMerge = {}
        for selection in self.param_selection_names:
            # layer: parameters for the selection from that layer
            layeredParamsToMerge[self.named_config[selection]["meta"]["layer"]] = self.named_config[selection]["parameters"]

        def recursive_merge(left, right):
            """Compare each entity.
            If one is not a dict, return right unless right is None.
            If both are dicts: -get a set of their keys and repeat this
                               - keys unique to either are kept. common keys replaced with right
            'left' and 'right' refers to the layer of provided dicts (left is lower).
            For more than two layers of config, this is called multiple times.
            e.g.: ((0 -> 1) -> 2) -> 3
            """
            if not isinstance(left, dict) or not isinstance(right, dict):
                return left if right is None else right
    
            else:  # Both left and right are dictionaries
                # A set of all the keys appearing in either dictionary is needed to iterate over

                keys = set(left.keys()) | set(right.keys())  # union set operator. set of both sets
                # Return one merged dictionary, searching nested dicts recursively.
                return {
                    key: recursive_merge(left.get(key), right.get(key))
                    for key in keys
                }
        
        paramsToMerge = []
        for i in range(len(self.layered_config)):  # layer_num
            if i in layeredParamsToMerge.keys():  # With continuous merge, may not have been chosen
                paramsToMerge.append(layeredParamsToMerge[i])
        # This orders them even with layers not chosen.
        
        config = paramsToMerge[0]
        for i in range(len(paramsToMerge) -1):  # with one choice made, len-1 = 0 so no merge.
            config = recursive_merge(config, paramsToMerge[i+1])

        return config

## original stuff below ##############################################

    def get_server_uptime(self):
        """Get the uptime for the ODIN server.

        This method returns the current uptime for the ODIN server.
        """
        return time.time() - self.init_time

    def get(self, path):
        """Get the parameter tree.

        This method returns the parameter tree for use by clients via the Manager adapter.

        :param path: path to retrieve from tree
        """
        return self.param_tree.get(path)

    def set(self, path, data):
        """Set parameters in the parameter tree.

        This method simply wraps underlying ParameterTree method so that an exceptions can be
        re-raised with an appropriate ManagerError.

        :param path: path of parameter tree to set values for
        :param data: dictionary of new data values to set in the parameter tree
        """
        self.latest_path = path  
        # store latest path in case it's needed e.g.: setter used for more than one thing (configs)
        try:
            self.param_tree.set(path, data)
        except ParameterTreeError as e:
            raise ManagerError(e)

    def post(self, path, data):
        """This is the same as set above.
        But has the additional requirement that new (posted) entries are added to the local vars.
        There is no provision in the ParameterTree setup to have a method for adding new ones
        as there is for editing existing ones (e.g.: `value: (lambda: getter, setter)`).

        This allows newly added values to then be accessed without requiring many database calls 
        (saving and retrieving), handling data locally as intended.
        POST is only used to add a new entry so the explicit handling here should be no issue.

        If the restart is demanded on adding a new one then this can just be set().
        """
        self.latest_path = path
        new = next(iter(data.values()))  # data is like {confName: {id, name, etc.}}
    
        try:
            self.param_tree.set(path, data)

            self.named_config[new["Name"]] = new
            self.all_configs.append(new)
            self.layered_config[new["meta"]["layer"]].append(new)

        except ParameterTreeError as e:
            raise ManagerError(e)