import sys
import os.path
from datetime import datetime
from django.core.management.base import BaseCommand
from django.conf import settings
from faxcelerate.fax.models import Fax

import logging
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    args = '<qfile why jobtime [nextTry]>'
    help = 'Processes outgoing fax user notification'

    def handle(self, *args, **options):

        if 3 > len(args) > 4:
            raise AttributeError

        TIFF_OUTPUT_DIR = os.path.join(settings.FAX_SPOOL_DIR, 'senttiff')

        qfile, why, jobtime = args[:3]

        # Scan qfile for info
        info = {}
        for line in open(os.path.join(settings.FAX_SPOOL_DIR, qfile), 'r'):
            tag, data = line.split(':', 1)
            data = data.strip()
            if tag[0] == '!':
                if not tag in info:
                    info[tag] = []
                info[tag].append(data)
            else:
                info[tag] = data
        print info

        try:
            fax = Fax.objects.get(comm_id=info['commid'])
        except Fax.DoesNotExist:
            fax = Fax()

        error_message = None
        if why != 'done' or int(info['state']) == 9:
            try:
                error_message = '%s: %s' % (why, info['status'])
            except KeyError:
                error_message = why
            fax.status = 2
        else:
            fax.status = 1
        print 'OK'

        # Continue if fax is done or aborted due to an error
        if why in ('blocked', 'requeued'):
            fax.status = 0
            fax.save()
            sys.exit(1)

        fax.comm_id = info['commid']
        fax.local_sender = '%s@%s' % (info['mailaddr'], info['client'])
        fax.received_on = datetime.fromtimestamp(float(info['tts']))
        fax.outbound = True
        fax.caller_id = info['number']
        if error_message:
            fax.reason = error_message
        # Exit if job is not done
        if int(info['state']) < 7:
            fax.save()
            sys.exit(1)

        # List files
        input_files = []
        for tag in ('postscript', 'pdf', '!postscript', '!pdf'):
            if tag in info:
                input_files += [os.path.join(settings.FAX_SPOOL_DIR,
                                             name.split(':')[-1]) for name in info[tag]]

        # Build TIFF file
        output_file = '%s.tif' % os.path.join(TIFF_OUTPUT_DIR, info['commid'])
        os.system('gs -dBATCH -dNOPAUSE -q -sDEVICE=tiffg3 -sOutputFile=%s %s -r200'
                  % (output_file, ' '.join(input_files)))

        # Store in DB
        fax.filename = 'senttiff/%s.tif' % info['commid']
        fax.time_to_receive = 1
        fax.update_from_tiff()
        fax.save()
        from faxcelerate.fax.image import FaxImage

        FaxImage(fax).cache_thumbnails()