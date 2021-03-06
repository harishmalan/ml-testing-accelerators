# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import re
import socket
from datetime import datetime

from absl import logging
import google.auth
import pandas as pd
import pandas_gbq
import redis

redis_host = os.environ.get('REDISHOST', 'localhost')
redis_port = int(os.environ.get('REDISPORT', 6379))
try:
  redis_client = redis.StrictRedis(host=redis_host, port=redis_port)
  redis_client.ping()
except Exception as e:
  logging.error('Error connecting to redis instance: {}'.format(e))
  redis_client = None


def _run(query, config={}):
  return pd.read_gbq(
      query,
      project_id=google.auth.default()[1],
      dialect='standard',
      configuration=config)


def run_query(query, cache_key, config={}, expire=3600):
  if not redis_client:
    logging.error('\n\n\nno redis_client\n\n\n')
    return _run(query, config=config)
  else:
    json = redis_client.get(cache_key)
    if json is not None:
      df = pd.read_json(json, orient='records')
    else:
      df = _run(query, config=config)
      redis_client.set(cache_key, df.to_json(orient='records'), ex=expire)
  return df


# TODO: Reconcile this with the similar helper method under
# metrics_handler/util.py
LOGS_DOWNLOAD_COMMAND = """gcloud logging read 'resource.type=k8s_container resource.labels.project_id={project} resource.labels.location={zone} resource.labels.cluster_name={cluster} resource.labels.namespace_name={namespace} resource.labels.pod_name:{pod}' --limit 10000000000000 --order asc --format 'value(textPayload)' --project={project} > {pod}_logs.txt && sed -i '/^$/d' {pod}_logs.txt"""
LOG_LINK_REGEX = re.compile('https://console\.cloud\.google\.com/logs\?project=(\S+)\&advancedFilter=resource\.type\%3Dk8s_container\%0Aresource\.labels\.project_id\%3D(?P<project>\S+)\%0Aresource\.labels\.location=(?P<zone>\S+)\%0Aresource\.labels\.cluster_name=(?P<cluster>\S+)\%0Aresource\.labels\.namespace_name=(?P<namespace>\S+)\%0Aresource\.labels\.pod_name:(?P<pod>\S+)(\&dateRangeUnbound=backwardInTime)?')
def get_download_command(logs_link):
  log_pieces = LOG_LINK_REGEX.match(logs_link)
  if not log_pieces:
    print('Could not parse log link to make download link. Logs link '
          'was: {}'.format(logs_link))
    return ''
  download_command = LOGS_DOWNLOAD_COMMAND.format(**log_pieces.groupdict())
  return download_command


