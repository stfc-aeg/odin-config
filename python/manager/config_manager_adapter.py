"""Demo adapter for ODIN config manager

This class implements the basic functionality needed for the config manager

Mika Shearwood, STFC Detector Systems Software Group
"""
import logging
from tornado.escape import json_decode

from manager.config_manager import ConfigManager, ConfigManagerError
from odin.adapters.adapter import ApiAdapter, ApiAdapterResponse, request_types, response_types
from odin.adapters.parameter_tree import ParameterTreeError


class ConfigManagerAdapter(ApiAdapter):
    """System info adapter class for the ODIN server.

    This adapter provides ODIN clients with information about the server and the system that it is
    running on.
    """

    def __init__(self, **kwargs):
        """Initialize the ConfigManagerAdapter object.

        This constructor initializes the ConfigManagerAdapter object.

        :param kwargs: keyword arguments specifying options
        """
        # Intialise superclass
        super(ConfigManagerAdapter, self).__init__(**kwargs)

        # Get connection string, db, collection and revision collection names from options
        # Default to demo: 'tormongo', 'Instrument', 'InstrumentHistory'
        if self.options.get('mongo_con_string', False):
            connection_string = self.options.get('mongo_con_string')
        else:
            connection_string = 'mongodb://localhost:27017'

        if self.options.get('database', False):
            db = self.options.get('database')
        else:
            db = 'tormongo'

        if self.options.get('collection_name', False):
            collection_name = self.options.get('collection_name')
        else:
            logging.debug("Setting config db collection to default: 'Instrument'.")
            collection_name = 'Instrument'

        if self.options.get('revision_collection_name', False):
            rev_collection_name = self.options.get('revision_collection_name')
        else:
            logging.debug("Setting config revision collection to default: 'InstrumentHistory'.")
            rev_collection_name = 'InstrumentHistory'

        self.config_manager = ConfigManager(connection_string, db,
                                            collection_name, rev_collection_name)

        self.get_current_config = self.config_manager.get_current_config
        self.register_callback = self.config_manager.register_callback

        logging.debug('ManagerAdapter loaded')

    def initialize(self, adapters):
        for name, adapter in adapters.items():
            if name == 'instrument':
                # We want the instrument class, not the instrumentAdapter
                # Adapter offers no extra useful functionality.
                self.config_manager.add_adapter(adapter.instrument)

    @response_types('application/json', default='application/json')
    def get(self, path, request):
        """Handle an HTTP GET request.

        This method handles an HTTP GET request, returning a JSON response.

        :param path: URI path of request
        :param request: HTTP request object
        :return: an ApiAdapterResponse object containing the appropriate response
        """
        try:
            response = self.config_manager.get(path)
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
            self.config_manager.post(path, data)
            response = self.config_manager.get(path)
            status_code = 200
        except ConfigManagerError as e:
            response = {'error': str(e)}
            status_code = 400
        except (TypeError, ValueError) as e:
            response = {'error': 'Failed to decode POST request body: {}'.format(str(e))}
            status_code = 400

        logging.debug(response)

        return ApiAdapterResponse(response, content_type=content_type,
                                  status_code=status_code)

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
            self.config_manager.set(path, data)
            response = self.config_manager.get(path)
            status_code = 200
        except ConfigManagerError as e:
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
        response = 'ConfigManagerAdapter: DELETE on path {}'.format(path)
        status_code = 200

        logging.debug(response)

        return ApiAdapterResponse(response, status_code=status_code)

    def cleanup(self):
        """Clean up adapter state at shutdown.

        This method cleans up the adapter state when called by the server at e.g. shutdown.
        It simplied calls the cleanup function of the ConfigManager instance.
        """
        self.config_manager.cleanup()
