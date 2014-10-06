import os.path
from datetime import datetime
from django.core.management.base import BaseCommand
from django.conf import settings
from faxcelerate.fax.models import Fax
from faxcelerate.fax.image import FaxImage

import logging
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    args = '<qfile devid commid error-msg [callid [callid-2 [callid-n ...]]]>'
    help = 'Processes fax'

    def handle(self, *args, **options):

        if len(args) < 4:
            raise AttributeError

        qfile, devid, commid, msg = map(str.rstrip, args[:4])
        callid = map(str.strip, args[4:])

        logger.info('Processing received fax %s', commid)
        logger.debug('Fax %s in file %s, received on device %s, message: %s', commid, qfile, devid, msg)

        filename = settings.FAX_SPOOL_DIR + '/' + qfile

        fax = Fax()
        fax.received_on = datetime.fromtimestamp(os.path.getmtime(filename))
        fax.filename = filename
        fax.device = devid
        fax.comm_id = commid
        fax.reason = msg
        fax.status = 1  # Success
        # TODO improve caller_id
        fax.caller_id = str(callid)

        try:
            fax.update_from_tiff()
        except ValueError, e:
            if msg:
                fax.error = True
                fax.status = 2  # Error
                logging.info("Fax %s has an error; reason: %s", commid, msg)
            else:
                raise e

        fax.update_from_logfile()
        if fax.station_id == fax.caller_id or fax.station_id == '-':
            fax.station_id = None
        fax.set_sender()
        fax.save()
        FaxImage(fax).cache_thumbnails()
