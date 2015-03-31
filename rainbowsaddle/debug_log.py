import logging

# Create a handler
file_handler = logging.FileHandler('/tmp/rainbow-saddle_debug.log')
file_handler.setLevel(logging.DEBUG)

# Create the logger
logger = logging.getLogger('debug_log')
logger.setLevel(logging.DEBUG)

# Create format
formatter = logging.Formatter('%(asctime)s - %(message)s')

file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

logger.debug('Started debug_log')
debug = logger.debug
