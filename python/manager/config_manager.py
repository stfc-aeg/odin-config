"""Demo adapter for ODIN config manager

This class implements the basic functionality needed for the config manager

Mika Shearwood, STFC Detector Systems Software Group
"""
import logging
import tornado
import time

from odin.adapters.parameter_tree import ParameterTree, ParameterTreeError
from odin._version import get_versions

import pymongo
from pymongo import MongoClient
from collections import Counter


class ConfigManagerError(Exception):
    """Simple exception class to wrap lower-level exceptions."""

    pass


class ConfigManager():
    """ConfigManager - class that reads MongoDB collections to store and handle information about
    configuration options.
    """

    def __init__(self, mongo_con_string, db, collection, revision_collection):
        """Initialise the ConfigManager object.

        This makes relevant database connections, accesses collections and builds
        mutable parameter trees.
        """
        # Initialise DB client and vars
        self.client = MongoClient(mongo_con_string)
        self.db = self.client[db]
        self.collection = collection  # collection accessed later

        # Set up then populate all config entry variables
        self.all_configs = []
        self.all_names = {}
        self.named_config = {}
        self.layered_config = {}
        self.ancestry = {}
        self.get_database_entries()

        self.historyCollection = self.db[revision_collection]  # collection name for instrument revisions
        # self.revision = self.get_all_revisions(self.historyCollection)

        self.adapters = []
        self.callbacks = {}

        # Store initialisation time
        self.init_time = time.time()

        # Get package version information
        version_info = get_versions()

        # Parameter tree for database
        self.param_selection_names = []
        self.param_selection = []
        self.reset_valid_options()
        self.used_layers = []

        db_tree = ParameterTree({
            'config_num': (lambda: len(self.all_configs), None),
            'layer_num': (lambda: len(self.layered_config), None),
            'param_selection_names': (lambda: self.param_selection_names, self.set_param_selection),
            'valid_options': (lambda: self.valid_options, self.set_valid_options),  # All are valid
            'current_config': (lambda: self.get_current_config(), None)
        })

        # Making a parameter tree of the configs. Need a get for the value otherwise it won't work.
        # This contains all details stored under the name, which needs to be unique for versioning.
        config_tree_dict = {}
        # Change tree stores all of the revisions for a given option.
        change_tree_dict = {}

        for entry in self.all_configs:
            config_tree_dict[entry["Name"]] = (
                self.get_named_config(entry["Name"]), self.set_config
            )
            change_tree_dict[entry["Name"]] = (
                self.get_config_revisions(entry["Name"]), None
            )

        config_tree = ParameterTree(config_tree_dict, mutable=True)
        change_tree = ParameterTree(change_tree_dict, mutable=True)

        # Store all information in a parameter tree
        self.param_tree = ParameterTree({
            'odin_version': version_info['version'],
            'tornado_version': tornado.version,
            'db_collection': (lambda: self.collection, None),
            'server_uptime': (self.get_server_uptime, None),
            'all_configs': config_tree,
            'config_revisions': change_tree,
            'selection': db_tree,
            'all_names': (self.all_names, None),
            'get_config': (lambda: None, self.push_callback)
        }, mutable=True)

    def add_adapter(self, adapter):
        """Add an adapter to the config manager's list of known adapters.

        :param adapter: the adapter to store reference to."""
        self.adapters.append(adapter)
        logging.debug("New adapter registered with config manager: {}.".format(adapter))

    def register_callback(self, adapter, callback):
        """Register a callback with another adapter.

        At present, accepts one callback per adapter, to push the config.

        :param adapter: adapter to store callback for
        :param callback: function to be called back.
        """
        if adapter not in self.callbacks:
            self.callbacks[adapter] = None
        self.callbacks[adapter] = callback  # One callback registered per adapter
        logging.debug("Received callback with adapter: {}.".format(adapter))

    def push_callback(self, data):
        """Activate the callback functions for pushing data."""
        for adapter in self.adapters:
            if adapter in self.callbacks.keys():
                self.callbacks[adapter]()

    def get_database_entries(self):
        """Get the data from mongo with the db specified in __init__.
        This accesses the database collection and performs the ancestry aggregation.
        It then constructs the relevant local collections of the information:
        - all configs  - sorted by name  - sorted by layer  - names sorted by layer
        """
        Instrument = self.db[self.collection]
        pipeline = [  # Array of aggregation steps
            {
                "$graphLookup":
                {
                    "from": self.collection,
                    "startWith": "$children",
                    "connectFromField": "children",
                    "connectToField": "Name",
                    "as": "descendants"
                }
            },
            {
                "$graphLookup":
                {
                    "from": self.collection,
                    "startWith": '$parents',
                    "connectFromField": 'parents',
                    "connectToField": "Name",
                    "as": 'ancestors'
                }
            },
            {
                "$sort":
                {
                    "layer": pymongo.ASCENDING
                }
            }
        ]
        results = Instrument.aggregate(pipeline)  # All configs with full family history
        all = []  # All configs in original form
        named = {}  # key:value, name:object
        layered = {}  # key:list, layer:(list of configs in layer)
        all_names = {}  # just the names of all the configs against layers.

        for result in results:
            all.append(result)

            named[result["Name"]] = result  # Dict sorted by name

            result_layer = result["meta"]["layer"]

            if result_layer not in layered.keys():  # Check if layer exists
                layered[result_layer] = []  # Create layer if it does not
                all_names[result_layer] = []
            layered[result_layer].append(result)
            all_names[result_layer].append(result["Name"])
        # Necessary to layer the 'all_names' for the UI to access on initialisation.

        ancestry = {}
        for config in all:
            ancestry[config["Name"]] = {
                "ancestors": config["ancestors"],
                "descendants": config["descendants"]
            }
            config.pop("ancestors")
            config.pop("descendants")
            # We have these in ancestry now and they take significant space

        self.all_configs = all
        self.all_names = all_names
        self.named_config = named
        self.layered_config = layered
        self.ancestry = ancestry

    def get_config_revisions(self, name):
        """Get all the revisions for a given config option.

        :param name: name of the config option to search for
        :return: list of all revisions of a config object
        """
        # This is accessed via request to tree for all config history options
        # If you request the entire change_tree that could get large over time.
        # Consider this potential future inefficiency when designing 'view history'.
        results = self.historyCollection.find({"Name": {"$eq": name}})
        revisions = []
        for result in results:
            revisions.append(result)

        return revisions

    def get_named_config(self, name):
        """Return the details of a given config."""
        return self.named_config[name]

    def set_config(self, request):
        """Set the specified config value to the replacement.
        Currently assumes that the access is done through all_configs/config_name.
        Final implementation depends on how the edit function operates.
        """
        # Expecting this to be done in one go, in essence show user an editable JSON file.
        # so you would just direct them to all_configs/confName and then replace the whole thing.
        # This currently assumes you go directly to e.g.: curlMode
        node = self.latest_path.split("/")[-2]  # self.path ends with /

        for key, item in request.items():
            self.named_config[node][key] = item

    def set_param_selection(self, names):
        """Set the current parameter selection to determine the valid options.

        Performs some checks to verify that the selection exists, has only one choice per layer,
        and that the options are compatible as the valid options are determined.
        This process assumes that multiple parameters are provided simultaneously (such as
        in one PUT request).

        :param names: the body of the PUT request. A list of parameter names.
        """
        self.param_selection_names = []  # If params selected one at a time, these lines go
        self.param_selection = []

        # No selection (i.e.: empty PUT)? Reset valid options and return
        if len(names) == 0:
            self.reset_valid_options()
            return

        # Order the parameter selections: e.g.: {0:None,1:param,2:None}
        ordered_selection_dict = {i: None for i in range(len(self.layered_config))}

        for name in names:
            num = self.named_config[name]["meta"]["layer"]

            # Check that each layer has only one option in it
            if ordered_selection_dict[num]:
                print("Select only one option per layer")
                return  # Do nothing

            # Place selection in layer
            ordered_selection_dict[num] = name

        for key, value in ordered_selection_dict.items():
            if value is None:  # If not chosen for that layer, skip it
                pass
            else:
                self.param_selection_names.append(value)
                self.param_selection.append(self.named_config[value])
                length = self.set_valid_options()

                # If no valid options and you've not yet selected one option per layer, invalid
                # key is an integer counting from zero, referring to layers
                if (length == 0) and (key != len(self.layered_config) - 1):
                    print("These options are incompatible, please select another combination.")
                    self.param_selection_names = []
                    self.param_selection = []
                    self.reset_valid_options()
                    return

        # Ignoring the check for incompatible options: you just add the ordered ones, in order, to
        # param_selection_names. Then call set_valid_options

    def set_valid_options(self):
        """Determine the valid options given the current parameter selection.

        This iterates over the list of selections, and finds all options that are relatives of
        every item in the selection and not in the same layer as the selection. Or, finds options
        in a common family tree to the selection.

        :return: the length of the valid options, for the checks in set_param_selection
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
        self.valid_options = {
            layer:
            [value["Name"] for value in values if value["Name"] in allOptions]
            for layer, values in self.layered_config.items()
        }  # Similar to reset_valid_options, with the condition that the names are in allOptions.

        return len(self.valid_options)

    def reset_valid_options(self):
        """Reset valid_options to the default state of every option being a valid choice."""
        self.valid_options = {   # reset
                layer:
                [value["Name"] for value in values]
                for layer, values in self.layered_config.items()
        }
        # For every layer, look at its list of values. Key = layer, value = list of all options

    def get_current_config(self):
        """Merge the current selection of options.

        If there is one selection, this is just that parameter's options.
        The merge will be re-done each time an option is added, because the order of merge matters
        and options are not necessarily selected in layer-order.

        :return: the full merged configuration, or a string if no selection has been made.
        """
        if len(self.param_selection_names) == 0:
            return "Select options to merge"  # If nothing has been selected, leave it blank

        layeredParamsToMerge = {}
        for selection in self.param_selection_names:
            # layer: parameters for the selection from that layer
            layeredParamsToMerge[
                self.named_config[selection]["meta"]["layer"]
                                ] = self.named_config[selection]["parameters"]

        def recursive_merge(left, right):
            """Merge two dictionaries.

            Compare the entities. If one is not a dictionary, return right unless right is None.
            If both are dicts, get a set of their keys and repeat for each key.
            For more than two layers of config, this will be called multiple times.
            e.g.: ((0 -> 1) -> 2) -> 3

            :param left: the 'left-most' dictionary. Lower priority.
            :param right: the 'right-most' dictionary to merge over left.
            :return: the merged configuration of two dictionaries, with right overriding left.
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
        for i in range(len(paramsToMerge) - 1):  # with one choice made, len-1 = 0 so no merge.
            config = recursive_merge(config, paramsToMerge[i+1])

        return config

    def get_server_uptime(self):
        """Get the uptime for the ODIN server.

        This method returns the current uptime for the ODIN server.
        """
        return time.time() - self.init_time

    def get(self, path):
        """Get the parameter tree.

        This method returns the parameter tree for use by clients via the ConfigManager adapter.

        :param path: path to retrieve from tree
        """
        return self.param_tree.get(path)

    def set(self, path, data):
        """Set parameters in the parameter tree.

        This method simply wraps underlying ParameterTree method so that an exceptions can be
        re-raised with an appropriate ConfigManagerError.

        :param path: path of parameter tree to set values for
        :param data: dictionary of new data values to set in the parameter tree
        """
        self.latest_path = path
        # store latest path in case it's needed e.g.: setter used for more than one thing (configs)
        try:
            self.param_tree.set(path, data)
        except ParameterTreeError as e:
            raise ConfigManagerError(e)

    def post(self, path, data):
        """This is the same as set above.
        But has the additional requirement that new (posted) entries are added to the local vars.
        There is no provision in the ParameterTree setup to have a method for adding new ones
        as there is for editing existing ones (e.g.: `value: (lambda: getter, setter)`).

        This allows newly added values to then be accessed without requiring many database calls
        (saving and retrieving), handling data locally as intended.
        POST is only used to add a new entry so the explicit handling here should be no issue.

        If the restart is demanded on adding a new entry then only set() is needed in try block.
        """
        self.latest_path = path
        new = next(iter(data.values()))  # data is like {confName: {id, name, etc.}}

        try:
            self.param_tree.set(path, data)

            # Add option to named_/all_/layered_config. Though, restart likely best choice.
            self.named_config[new["Name"]] = new
            self.all_configs.append(new)
            self.layered_config[new["meta"]["layer"]].append(new)

        except ParameterTreeError as e:
            raise ConfigManagerError(e)
