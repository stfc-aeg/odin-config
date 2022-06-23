"""A dummy adapter to test the push/pull mechanisms for config retrieval from the config manager


Mika Shearwood, STFC Detector Systems Software Group
"""
import logging
import time
import tornado

from tornado.escape import json_decode

from odin.adapters.adapter import ApiAdapter, ApiAdapterResponse, request_types, response_types
from odin.adapters.parameter_tree import ParameterTree, ParameterTreeError
from odin._version import get_versions


class InstrumentAdapter(ApiAdapter):
    """System info adapter class for the ODIN server.

    This adapter provides ODIN clients with information about the server and the system that it is
    running on.
    """

    def __init__(self, **kwargs):
        """Initialize the InstrumentAdapter object.

        This constructor initializes the InstrumentAdapter object.

        :param kwargs: keyword arguments specifying options
        """
        # Intialise superclass
        super(InstrumentAdapter, self).__init__(**kwargs)

        self.instrument = Instrument()

        logging.debug('InstrumentAdapter loaded')

    def initialize(self, adapters):
        for name, adapter in adapters.items():
            if name == 'config_manager':
                self.instrument.set_config_manager(adapter.config_manager)

                adapter.config_manager.register_callback(adapter=self.instrument,
                                                  callback=self.instrument.get_config)
                logging.debug("Registered callback with manager adapter.")

    @response_types('application/json', default='application/json')
    def get(self, path, request):
        """Handle an HTTP GET request.

        This method handles an HTTP GET request, returning a JSON response.

        :param path: URI path of request
        :param request: HTTP request object
        :return: an ApiAdapterResponse object containing the appropriate response
        """
        try:
            response = self.instrument.get(path)
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
            self.instrument.post(path, data)
            response = self.instrument.get(path)
            status_code = 200
        except InstrumentError as e:
            response = {'error': str(e)}
            status_code = 400
        except (TypeError, ValueError) as e:
            response = {'error': 'Failed to decode POST request body: {}'.format(str(e))}
            status_code = 400

        logging.debug(response)

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
            self.instrument.set(path, data)
            response = self.instrument.get(path)
            status_code = 200
        except InstrumentError as e:
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
        response = 'InstrumentAdapter: DELETE on path {}'.format(path)
        status_code = 200

        logging.debug(response)

        return ApiAdapterResponse(response, status_code=status_code)

    def cleanup(self):
        """Clean up adapter state at shutdown.

        This method cleans up the adapter state when called by the server at e.g. shutdown.
        It simplied calls the cleanup function of the instrument instance.
        """
        self.instrument.cleanup()


class InstrumentError(Exception):
    """Simple exception class to wrap lower-level exceptions."""

    pass


class Instrument():

    def __init__(self):

        # Store initialisation time
        self.init_time = time.time()

        # Get package version information
        version_info = get_versions()

        self.config_manager = None
        self.config = None

        # param variables which would be some default value?
        self.curious_num = 0
        self.specific_num = 0
        self.random_num = 0

        self.param_param_tree = ParameterTree({
            'curious_num': (lambda: self.curious_num, self.set_params),
            'specific_num': (lambda: self.specific_num, self.set_params),
            'random_num': (lambda: self.random_num, self.set_params),
        })

        self.param_tree = ParameterTree({
            'odin_version': version_info['version'],
            'tornado_version': tornado.version,
            'server_uptime': (self.get_server_uptime, None),
            'certain_params': self.param_param_tree,
            'request_config': (lambda: None, self.get_config),
        })

    def set_config_manager(self, manager):
        """Store the config manager adapter in a class variable."""
        self.config_manager = manager

    def get_config(self, data=None):  # data=None as this can be called from PUT commands
        """Get the current config from the config manager."""
        self.config = self.config_manager.get_current_config()
        self.set_params()

    def set_params(self):
        """Set parameters in the tree based on the current config."""
        if type(self.config) is dict:
            # Currently using some sample data from the demo database
            if self.key_verify(self.config, "subtree", "curious_num"):
                self.curious_num = self.config["subtree"]["curious_num"]
            if self.key_verify(self.config, "subtree", "specific_num"):
                self.specific_num = self.config["subtree"]["specific_num"]
            if self.key_verify(self.config, "subtree", "random_num"):
                self.random_num = self.config["subtree"]["random_num"]
        else:
            self.curious_num, self.specific_num, self.random_num = 0, 0, 0  # Reset

    def key_verify(self, data, *keys):
        """Verify that a particular sequence of nested keys exists in a dictionary.
        """
        _data = data
        for key in keys:
            try:
                _data = _data[key]
            except KeyError:
                return False
        return True

    def get_server_uptime(self):
        """Return the current uptime for the ODIN Server."""
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
        try:
            self.param_tree.set(path, data)
        except ParameterTreeError as e:
            raise InstrumentError(e)

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

        try:
            self.param_tree.set(path, data)
        except ParameterTreeError as e:
            raise InstrumentError(e)
