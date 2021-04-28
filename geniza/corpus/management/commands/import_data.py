import codecs
import csv
import logging
import re
import os
from collections import defaultdict, namedtuple
from datetime import datetime
from operator import itemgetter
from string import punctuation

import requests
from dateutil.parser import ParserError, parse
from django.conf import settings
from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, models
from django.utils.text import slugify
from django.utils.timezone import get_current_timezone, make_aware

from geniza.corpus.models import (Collection, Document, DocumentType, Fragment,
                                  LanguageScript, TextBlock)
from geniza.footnotes.models import Creator, Footnote, Source, SourceLanguage,\
    SourceType

# mapping for csv header fields and local name we want to use
# if not specified, column will be lower-cased
csv_fields = {
    'libraries': {
        'Current List of Libraries': 'current',
        'Library abbreviation': 'lib_abbrev',
        'Collection abbreviation': 'abbrev',
        'Location (current)': 'location',
        'Collection (if different from library)': 'collection'
    },
    'languages': {
        # lower case for each should be fine
    },
    'metadata': {
        'Shelfmark - Current': 'shelfmark',
        'Input by (optional)': 'input_by',
        'Date entered (optional)': 'date_entered',
        'Recto or verso (optional)': 'recto_verso',
        'Language (optional)': 'language',
        'Text-block (optional)': 'text_block',
        'Shelfmark - Historical (optional)': 'shelfmark_historic',
        'Multifragment (optional)': 'multifragment',
        'Link to image': 'image_link',
        'Editor(s)': 'editor',
        'Translator (optional)': 'translator'
    }
}

# events in document edit history with missing/malformed dates will replace
# missing portions with values from this date
DEFAULT_EVENT_DATE = datetime(2020, 1, 1)

# logging config: use levels as integers for verbosity option
logger = logging.getLogger("import")
logging.basicConfig()
LOG_LEVELS = {
    0: logging.ERROR,
    1: logging.WARNING,
    2: logging.INFO,
    3: logging.DEBUG
}


class Command(BaseCommand):
    'Import existing data from PGP spreadsheets into the database'

    logentry_message = 'Imported via script'

    content_types = {}
    collection_lookup = {}
    document_type = {}
    language_lookup = {}
    user_lookup = {}
    max_documents = None

    def add_arguments(self, parser):
        parser.add_argument('-m', '--max_documents', type=int)

    def setup(self, *args, **options):
        if not hasattr(settings, 'DATA_IMPORT_URLS'):
            raise CommandError(
                'Please configure DATA_IMPORT_URLS in local settings')

        # setup logging; default to WARNING level
        verbosity = options.get("verbosity", 1)
        logger.setLevel(LOG_LEVELS[verbosity])

        # load fixure containing known historic users (all non-active)
        call_command("loaddata", "historic_users",
                     app_label="corpus", verbosity=0)
        logger.info("loaded 30 historic users")

        # ensure current active users are present, but don't try to create them
        # in a test environment because it's slow and requires VPN access
        active_users = ["rrichman", "mrustow", "ae5677", "alg4"]
        if "PYTEST_CURRENT_TEST" not in os.environ:
            present = User.objects.filter(username__in=active_users) \
                                  .values_list("username", flat=True)
            for username in set(active_users) - set(present):
                call_command("createcasuser", username, staff=True,
                             verbosity=verbosity)

        # fetch users created through migrations for easy access later; add one
        # known exception (accented character)
        self.script_user = User.objects.get(username=settings.SCRIPT_USERNAME)
        self.team_user = User.objects.get(username=settings.TEAM_USERNAME)
        self.user_lookup["Naim Vanthieghem"] = User.objects.get(
            username="nvanthieghem")

        self.content_types = {
            model: ContentType.objects.get_for_model(model)
            for model in [Fragment, Collection, Document, LanguageScript]
        }

        self.source_setup()

    def source_setup(self):
        # setup for importing editions & transcriptions

        # delete source records created on a previous run
        Creator.objects.all().delete()
        Source.objects.all().delete()  # should cascade to footnotes

        # load fixure with source creators referenced in the spreadsheet
        call_command("loaddata", "source_authors",
                     app_label="footnotes", verbosity=0)
        # total TODO
        # logger.info("loaded ## source creators")

        # create source type lookup keyed on type
        self.source_types = {
            s.type: s for s in SourceType.objects.all()
        }
        # create source creator lookup keyed on last name
        self.source_creators = {
            c.last_name: c for c in Creator.objects.all()
        }

    def handle(self, *args, **options):
        self.setup(*args, **options)
        self.max_documents = options.get("max_documents")
        self.import_collections()
        self.import_languages()
        self.import_documents()

    def get_csv(self, name):
        # given a name for a file in the configured data import urls,
        # load the data by url and initialize and return a generator
        # of namedtuple elements for each row
        csv_url = settings.DATA_IMPORT_URLS.get(name, None)
        if not csv_url:
            raise CommandError('Import URL for %s is not configured' % name)
        response = requests.get(csv_url, stream=True)
        if response.status_code != requests.codes.ok:
            raise CommandError('Error accessing CSV for %s: %s' %
                               (name, response))

        csvreader = csv.reader(codecs.iterdecode(response.iter_lines(),
                                                 'utf-8'))
        header = next(csvreader)
        # Create a namedtuple based on headers in the csv
        # and local mapping of csv names to access names
        CsvRow = namedtuple('%sCSVRow' % name, (
            csv_fields[name].get(
                col,
                slugify(col).replace('-', '_') or 'empty_%d' % i)
            for i, col in enumerate(header)
            # NOTE: allows one empty header; more will cause an error
        ))

        # iterate over csv rows and yield a generator of the namedtuple
        for count, row in enumerate(csvreader, start=1):
            yield CsvRow(*row)
            # if max documents is configured, bail out for metadata
            if self.max_documents and name == 'metadata' and \
               count >= self.max_documents:
                break

    def import_collections(self):
        # clear out any existing collections
        Collection.objects.all().delete()
        # import list of libraries and abbreviations
        # convert to list so we can iterate twice
        library_data = list(self.get_csv('libraries'))

        # create a collection entry for every row in the sheet with both
        # required values
        collections = []
        # at the same time, populate a library lookup to map existing data
        for row in library_data:
            # must have at least library or collection
            if row.library or row.collection:
                new_collection = Collection.objects.create(
                    library=row.library,
                    lib_abbrev=row.lib_abbrev,
                    abbrev=row.abbrev,
                    location=row.location,
                    name=row.collection)
                collections.append(new_collection)

                # add the new object to library lookup
                # special case: CUL has multiple collections which use the
                # same library code in the metadata spreadsheet;
                # include collection abbreviation in lookup
                lookup_code = row.current
                if row.current == 'CUL':
                    lookup_code = '%s_%s' % (row.current, row.abbrev)
                self.collection_lookup[lookup_code] = new_collection

        # create log entries to document when & how records were created
        self.log_creation(*collections)
        logger.info('Imported %d collections' % len(collections))

    def import_languages(self):
        LanguageScript.objects.all().delete()
        language_data = self.get_csv('languages')
        languages = []
        for row in language_data:
            # skip empty rows
            if not row.language and not row.script:
                continue

            lang = LanguageScript.objects.create(
                language=row.language,
                script=row.script,
                display_name=row.display_name or None)

            # populate lookup for associating documents & languages;
            # use lower case spreadsheet name if set, or display name
            if row.display_name or row.spreadsheet_name:
                self.language_lookup[(row.spreadsheet_name or
                                      row.display_name).lower()] = lang
            languages.append(lang)

        # create log entries
        self.log_creation(*languages)
        logger.info('Imported %d languages' % len(languages))

    def add_document_language(self, doc, row):
        '''Parse languages and set probable_language and language_notes'''
        notes_list = []
        if not row.language:
            return

        for lang in row.language.split(';'):
            lang = lang.strip()
            # Place language in the language note if there're any non-question
            # mark notes in language entry
            if re.search(r'\([^?]+\)', lang):
                notes_list.append(lang)
            is_probable = '?' in lang
            # remove parentheticals, question marks, "some"
            lang = re.sub(r'\(.+\)', '', lang).replace('some', '').strip('? ')

            lang_model = self.language_lookup.get(lang.lower())
            if not lang_model:
                logger.error(
                    f'language not found. PGPID: {row.pgpid}, Language: {lang}')
            else:
                if is_probable:
                    doc.probable_languages.add(lang_model)
                else:
                    doc.languages.add(lang_model)

        if notes_list:
            doc.language_note = '\n'.join(notes_list)
            doc.save()

    def import_documents(self):
        metadata = self.get_csv('metadata')
        Document.objects.all().delete()
        Fragment.objects.all().delete()
        LogEntry.objects.filter(
            content_type_id=self.content_types[Document].id).delete()

        # create a reverse lookup for recto/verso labels used in the
        # spreadsheet to the codes used in the database
        recto_verso_lookup = {
            label.lower(): code
            for code, label in TextBlock.RECTO_VERSO_CHOICES
        }

        joins = []
        docstats = defaultdict(int)
        for row in metadata:
            if ';' in row.type:
                logger.warning('skipping PGPID %s (demerge)' % row.pgpid)
                docstats['skipped'] += 1
                continue

            doctype = self.get_doctype(row.type)
            fragment = self.get_fragment(row)
            doc = Document.objects.create(
                id=row.pgpid,
                doctype=doctype,
                description=row.description,
            )
            doc.tags.add(*[tag.strip() for tag in
                           row.tags.split('#') if tag.strip()])
            # associate fragment via text block
            TextBlock.objects.create(
                document=doc,
                fragment=fragment,
                # convert recto/verso value to code
                side=recto_verso_lookup.get(row.recto_verso, ''),
                extent_label=row.text_block,
                multifragment=row.multifragment
            )
            self.add_document_language(doc, row)
            docstats['documents'] += 1
            # create log entries as we go
            self.log_edit_history(doc, self.get_edit_history(row.input_by,
                                                             row.date_entered,
                                                             row.pgpid))
            # parse editor & translator information to create sources
            # and associate with footnotes
            editor = row.editor.strip('.')
            if editor and editor not in self.editor_ignore:
                self.parse_editor(doc, editor)
            # treat translator like editor, but set translation flag
            if row.translator:
                self.parse_editor(doc, row.translator, translation=True)

            # keep track of any joins to handle on a second pass
            if row.joins.strip():
                joins.append((doc, row.joins.strip()))

        # handle joins collected on the first pass
        for doc, join in joins:
            initial_shelfmark = doc.shelfmark
            for shelfmark in join.split(' + '):
                # skip the initial shelfmark, already associated
                if shelfmark == initial_shelfmark:
                    continue
                # get the fragment if it already exists
                join_fragment = Fragment.objects.filter(
                    shelfmark=shelfmark).first()
                # if not, create a stub fragment record
                if not join_fragment:
                    join_fragment = Fragment.objects.create(
                        shelfmark=shelfmark)
                    self.log_creation(join_fragment)
                # associate the fragment with the document
                doc.fragments.add(join_fragment)

        # update id sequence based on highest imported pgpid
        self.update_document_id_sequence()
        logger.info(
            'Imported %d documents, %d with joins; skipped %d' %
            (docstats['documents'], len(joins), docstats['skipped']))

    doctype_lookup = {}

    def get_doctype(self, dtype):
        # don't create an empty doctype
        dtype = dtype.strip()
        if not dtype:
            return

        doctype = self.doctype_lookup.get(dtype)
        # if not yet in our local lookup, get from the db
        if not doctype:
            doctype = DocumentType.objects.get_or_create(name=dtype)[0]
            self.doctype_lookup[dtype] = doctype

        return doctype

    def get_collection(self, data):
        lib_code = data.library.strip()
        # differentiate CUL collections based on shelfmark
        if lib_code == 'CUL':
            for cul_collection in ['T-S', 'CUL Or.', 'CUL Add.']:
                if data.shelfmark.startswith(cul_collection):
                    lib_code = 'CUL_%s' % cul_collection.replace('CUL ', '')
                    break
            # if code is still CUL, there is a problem
            if lib_code == 'CUL':
                logger.warning(
                    'CUL collection not determined for %s'
                    % data.shelfmark)
        return self.collection_lookup.get(lib_code)

    def get_fragment(self, data):
        # get the fragment for this document if it already exists;
        # if it doesn't, create it
        fragment = Fragment.objects.filter(shelfmark=data.shelfmark).first()
        if fragment:
            return fragment

        # if fragment was not found, create it
        fragment = Fragment.objects.create(
            shelfmark=data.shelfmark,
            # todo: handle missing libraries (set from shelfmark?)
            collection=self.get_collection(data),
            old_shelfmarks=data.shelfmark_historic,
            is_multifragment=bool(data.multifragment),
            url=data.image_link,
            iiif_url=self.get_iiif_url(data)
        )
        # log object creation
        self.log_creation(fragment)
        return fragment

    def get_iiif_url(self, data):
        '''Get IIIF Manifest URL for a fragment when possible'''

        # cambridge iiif manifest links use the same id as view links
        # NOTE: should exclude search link like this one:
        # https://cudl.lib.cam.ac.uk/search?fileID=&keyword=T-s%2013J33.12&page=1&x=0&y=
        extlink = data.image_link
        if 'cudl.lib.cam.ac.uk/view/' in extlink:
            iiif_link = extlink.replace('/view/', '/iiif/')
            # view links end with /1 or /2 but iiif link does not include it
            iiif_link = re.sub(r'/\d$', '', iiif_link)
            return iiif_link

        # TODO: get new figgy iiif urls for JTS images based on shelfmark
        # if no url, return empty string for blank instead of null
        return ''

    def log_creation(self, *objects):
        # create log entries to document when & how records were created
        # get content type based on first object
        content_type = self.content_types[objects[0].__class__]
        for obj in objects:
            LogEntry.objects.log_action(
                user_id=self.script_user.id,
                content_type_id=content_type.pk,
                object_id=obj.pk,
                object_repr=str(obj),
                change_message=self.logentry_message,
                action_flag=ADDITION)

    def get_user(self, name, pgpid=None):
        """Find a user account based on a provided name, using a simple cache.

        If not found, tries to use first/last initials for lookup. If all else
        fails, use the generic team account (TEAM_USERNAME).
        """

        # check the cache first
        user = self.user_lookup.get(name)
        if user:
            logger.debug(
                f"using cached user {user} for {name} on PGPID {pgpid}")
            return user

        # person with given name(s) and last name – case-insensitive lookup
        if " " in name:
            given_names, last_name = [sname.strip(punctuation) for sname in
                                      name.rsplit(" ", 1)]
            try:
                user = User.objects.get(first_name__iexact=given_names,
                                        last_name__iexact=last_name)
            except User.DoesNotExist:
                pass

        # initials; use first & last to do lookup
        elif name:
            name = name.strip(punctuation)
            first_i, last_i = name[0], name[-1]
            try:
                user = User.objects.get(first_name__startswith=first_i,
                                        last_name__startswith=last_i)
            except User.DoesNotExist:
                pass

        # if we didn't get anyone through either method, warn and use team user
        if not user:
            logger.warning(
                f"couldn't find user {name} on PGPID {pgpid}; using {self.team_user}")
            return self.team_user

        # otherwise add to the cache using requested name and return the user
        logger.debug(f"found user {user} for {name} on PGPID {pgpid}")
        self.user_lookup[name] = user
        return user

    def get_edit_history(self, input_by, date_entered, pgpid=None):
        """Parse spreadsheet "input by" and "date entered" columns to
        reconstruct the edit history of a single document.

        Output is a list of dict to pass to log_edit_history. Each event has
        a type (django log entry action flag), associated user, and date.

        This method is designed to output a list of events that matches the
        logic of the spreadsheet and is easy to reason about (chronologically
        ordered).
        """

        # split both fields by semicolon delimiter & remove whitespace
        all_input = [i.strip() for i in input_by.split(";")]
        all_dates = [d.strip() for d in date_entered.split(";")]

        # try to map every "input by" listing to a user account. for coauthored
        # events, add both users to a list – otherwise it's a one-element list
        # with the single user
        users = []
        for input_by in all_input:
            users.append([self.get_user(u, pgpid)
                          for u in input_by.split(" and ")])

        # convert every "date entered" listing to a date object. if any parts of
        # the date are missing, fill with default values below. for details:
        # https://dateutil.readthedocs.io/en/stable/parser.html#dateutil.parser.parse
        dates = []
        for date in all_dates:
            try:
                dates.append(parse(date, default=DEFAULT_EVENT_DATE).date())
            except ParserError:
                logger.warning(f"failed to parse date {date} on PGPID {pgpid}")

        # make sure we have same number of users/dates by padding with None;
        # later we can assign missing users to the generic team user
        while len(users) < len(dates):
            users.insert(0, None)

        # moving backwards in time, pair dates with users and event types.
        # when there is a mismatch between number of users and dates, we want
        # to associate the more recent dates with users, since in general
        # we have more information the closer to the present we are. if we run
        # out of users to assign, we use the generic team user.
        events = []
        users.reverse()
        all_dates.reverse()
        for i, date in enumerate(reversed(dates)):

            # earliest date is creation; all others are revisions
            event_type = CHANGE if i < len(dates) - 1 else ADDITION

            # if we have a date without a user, assign to the whole team
            user = users[i] or (self.team_user,)

            # create events with this date and type for all the matching users.
            # if there was more than one user (coauthor), use the same type and
            # date to represent the coauthorship
            for u in user:
                events.append({
                    "type": event_type,
                    "user": u,
                    "date": date,
                    "orig_date": all_dates[i],
                })
            if len(user) > 1:
                logger.debug(
                    f"found coauthored event for PGPID {pgpid}: {events[-2:]}")
            else:
                logger.debug(f"found event for PGPID {pgpid}: {events[-1]}")

        # sort chronologically and return
        events.sort(key=itemgetter("date"))
        return events

    sheet_add_msg = "Initial data entry (spreadsheet)"
    sheet_chg_msg = "Major revision (spreadsheet)"

    def log_edit_history(self, doc, events):
        """Given a Document and a sequence of events from get_edit_history,
        create corresponding Django log entries to represent that history.

        Always creates an entry by the script user (`SCRIPT_USERNAME`) with a
        timestamp of now to mark the import event itself.

        Optional `events` is list of dict from get_edit_history. Each event has
        a type (creation or revision), associated user, and timestamp.
        """

        # for each historic event, create a corresponding django log entry.
        # we use objects.create() instead of the log_action helper so that we
        # can control the timestamp.
        for event in events:
            dt = datetime(year=event["date"].year,
                          month=event["date"].month,
                          day=event["date"].day)
            msg = self.sheet_add_msg if event["type"] == ADDITION else self.sheet_chg_msg
            LogEntry.objects.create(
                user=event["user"],                            # FK in django
                content_type=self.content_types[Document],     # FK in django
                object_id=str(doc.pk),         # TextField in django
                object_repr=str(doc)[:200],    # CharField with limit in django
                change_message=f"{msg}, dated {event['orig_date']}",
                action_flag=event["type"],
                action_time=make_aware(dt, timezone=get_current_timezone()),
            )

        # log the actual import event as an ADDITION, since it marks the point
        # at which the object entered this database.
        LogEntry.objects.log_action(
            user_id=self.script_user.id,
            content_type_id=self.content_types[Document].pk,
            object_id=doc.pk,
            object_repr=str(doc),
            change_message=self.logentry_message,
            action_flag=ADDITION
        )

    def update_document_id_sequence(self):
        # set postgres document id sequence to maximum imported pgpid
        cursor = connection.cursor()
        cursor.execute(
            "SELECT setval('corpus_document_id_seq', max(id)) FROM corpus_document;")

    re_url = re.compile(r'(?P<url>https://[^ ]+)')

    # ignore these entries in the editor field:
    editor_ignore = [
        'awaiting transcription',
        'transcription listed on fgp',
        'transcription listed on fgp, awaiting digitization on pgp',
        'transcription listed in fgp, awaiting digitization on pgp',
        'source of transcription not noted in original pgp database',
        'yes',
        'partial transcription listed in fgp, awaiting digitization on pgp.',
        'partial transcription listed in fgp, awaiting digitization on pgp',
        'transcription (recto only) listed in fgp, awaiting digitization on pgp',
    ]

    re_docrelation = re.compile(r'^(. Also )?Ed. (and transl?.)? ?',
                                flags=re.I)

    # notes that may occur with an edition
    # - full transcription listed/awaiting ...
    # - with (minor) ..
    # - with corrections
    # - multiword parenthetical at the end of the edition

    re_ed_notes = re.compile(
        r'[.;] (?P<note>(' +
        r'(full )?transcription (listed|awaiting).*$|' +
        r'(with )?minor|with corrections).*$|' +
        r'awaiting digitization.*$|' +
        r'; edited (here )?in comparison with.*$|' +
        r'\. see .*$|' +
        r'(\(\w+ [\w ]+\) ?$))',
        flags=re.I)

    # regexes to pull out page or document location
    re_page_location = re.compile(
        r'[,.] (?P<pages>((pp?|pgs)\. ?\d+([-–]\d+)?)|(\d+[-–]\d+))\.?',
        flags=re.I)
    re_doc_location = re.compile(
        r'(, )?\(?(?P<doc>(Doc. #?|#)([A-Z]-)?\d+)\)?\.?',
        flags=re.I)
    # \u0590-\u05fe = range for hebrew characters
    re_goitein_section = re.compile(
        r' (?P<p>(\d+?[\u0590-\u05fe]|[\u0590-\u05fe]\d+)[\u0590-\u05fe]?)',
        flags=re.I)

    def parse_editor(self, document, editor, translation=False):
        # multiple editions are indicated by "; also ed."  or ". also ed."
        # split so we can parse each edition separately and add a footnote
        editions = re.split(r'[;.] (?=also ed\.|ed\.|also)',
                            editor, flags=re.I)

        for edition in editions:
            # strip whitespace and periods before checking ignore list
            if edition.rstrip(' .').lower() in self.editor_ignore:
                continue

            # footnotes for these records are always editions
            doc_relation = {Footnote.EDITION}
            # if importing from translator column, also set translation
            if translation:
                doc_relation.add(Footnote.TRANSLATION)
            notes = []
            location = []
            # copy the edition text before removing any notes or
            # other information
            edition_text = edition

            # beginning usually includes indicator if edition or edition
            # or translation
            edit_transl_match = self.re_docrelation.match(edition)
            if edit_transl_match:
                # if doc relation text includes translation, set flag
                if "and trans" in edit_transl_match.group(0):
                    doc_relation.add(Footnote.TRANSLATION)

                # remove ed/trans from edition text
                edition_text = self.re_docrelation.sub('', edition_text)

            ed_notes_match = self.re_ed_notes.search(edition_text)
            if ed_notes_match:
                # save the notes to add to the footnote
                # remove from the edition before parsing
                edition_text = self.re_ed_notes.sub('', edition_text)
                notes.append(ed_notes_match.groupdict()['note'])

            # if reference includes document or page location,
            # remove and store for footnote location
            doc_match = self.re_doc_location.search(edition_text)
            if doc_match:
                location.append(doc_match.groupdict()['doc'])
                edition_text = self.re_doc_location.sub('', edition_text)
            page_match = self.re_page_location.search(edition_text)
            if page_match:
                location.append(page_match.groupdict()['pages'])
                edition_text = self.re_page_location.sub('', edition_text)
            gsection_match = self.re_goitein_section.search(edition_text)
            if gsection_match:
                location.append(gsection_match.groupdict()['p'])
                edition_text = self.re_goitein_section.sub('', edition_text)

            # remove any whitespace left after pulling out notes and location
            # and strip any trailing punctuation
            edition_text = edition_text.strip(' .,;')
            try:
                source = self.get_source(edition_text, document)
                fn = Footnote(source=source, content_object=document,
                              doc_relation=doc_relation,
                              location=', '.join(location),
                              notes='\n'.join(notes))
                fn.save()
            except KeyError as err:
                logger.error('Error parsing PGDID %d editor %s: %s' %
                             (document.id, edition, err))

    def get_source_creator(self, name):
        # last name is always present, and last names are unique
        lastname = name.rsplit(' ')[-1]
        try:
            return self.source_creators[lastname]
        except Exception:
            logger.error('Source creator not found for %s' % name)
            raise

    def get_source(self, edition, document):
        # parse the edition information and get the source for this scholarly
        # record if it already exists; if it doesn't, create it

        # create a list of text to add to notes
        note_lines = []   # notes probably apply to footnote, not source

        # check for url and store if present
        url_match = self.re_url.search(edition)
        url = ''
        if url_match:
            # save the url, and remove from edition text, to simplify parsing
            url = url_match.group('url')
            edition = edition.replace(url, '').strip()

        # check for 4-digit year and store it if present
        year = None
        # one record has a date range; others have a month
        year_match = re.search(r'\b(?P<match>(\d{4}[––]|\d{2}/)?(?P<year>\d{4}))\b',
                               edition)
        if year_match:
            # store the year
            year = year_match.group('year')
            # check full match against year; if they differ, add to notes
            full_match = year_match.group('match')
            if full_match != year:
                note_lines.append(full_match)
                edition = edition.replace(full_match, '').strip(' .,')

        # no easy way to recognize more than two authors,
        # but there are only three instances
        special_cases = [
            'Lorenzo Bondioli, Tamer el-Leithy, Joshua Picard, Marina Rustow and Zain Shirazi',
            'Khan, el-Leithy, Rustow and Vanthieghem',
            'Oded Zinger, Naim Vanthieghem and Marina Rustow',
        ]
        ed_parts = None
        for special_case in special_cases:
            if edition.startswith(special_case):
                ed_parts = [edition[:len(special_case)],
                            edition[len(special_case):]]

        # if not a special case, split normally
        if not ed_parts:
            # split into chunks on commas, parentheses, brackets, semicolons
            ed_parts = [p.strip() for p in re.split(r'[,()[\];]', edition)]

        # authors always listed first
        author_names = re.split(r', | and ', ed_parts.pop(0))
        authors = []
        for author in author_names:
            authors.append(self.get_source_creator(author))

        # set defaults for information that may not be present
        title = volume = language = location = ''
        # if there are more parts, the second is the title
        if ed_parts:
            title = ed_parts.pop(0).strip()

        # determine source type
        if "diss" in edition:
            src_type = 'Dissertation'
        elif not title:
            src_type = 'Unpublished'
        elif any([term in edition for term in
                 ["typed texts", "unpublished", "handwritten texts"]]):
            src_type = 'Unpublished'
        # title with quotes indicates Article
        elif title[0] in ["'", '"']:
            src_type = 'Article'
        # if it isn't anything else, it's a book
        else:
            src_type = 'Book'

        # strip any quotes from beginning and end of title
        title = title.strip('"\'').strip()

        # figure out what the rest of the pieces are, if any
        for part in ed_parts:
            # vol. indicates volume
            if 'vol.' in part:
                volume = part.replace('vol.', '').strip()
            elif any([val in part for val in ['Doc', 'pp.', '#', ' at ']]):
                location = part
            elif part in ['Hebrew', 'German']:
                language = part
            # otherwise, stick it in the notes
            else:
                note_lines.append(part)

        # look to see if this source already exists
        # (no title indicates pgp-only edition)
        extra_opts = {}
        # if there is no title but there is a year, include in filter
        if not title and year:
            extra_opts['year'] = year

        # when multiple authors are present, we want to match *all* of them
        # filter on combination of last names AND total count
        author_filter = models.Q()
        author_count = len(authors)
        for a in authors:
            author_filter = author_filter & \
                models.Q(authors__last_name=a.last_name)

        sources = Source.objects \
            .annotate(author_count=models.Count('authorship')) \
            .filter(
                title=title, volume=volume,
                source_type__type=src_type,
                author_count=author_count,
                **extra_opts) \
            .filter(author_filter) \
            .distinct()

        if sources.count() > 1:
            # FIXME: is empty volume not filtering?
            print([s for s in sources])
            print([s.author_count for s in sources])
            print('author count %d' % author_count)
            logger.warn(
                'Found multiple sources for %s, %s (%s)' %
                ('; '.join([a.last_name for a in authors]),
                 title, src_type))
            print(sources)

        source = sources.first()
        if source:
            updated = False
            # set year if available and not already set
            if title and not source.year and year:
                source.year = year
                updated = True

            # if there is any note information, add to existing notes
            if note_lines:
                if source.notes:
                    note_lines.insert(0, source.notes)
                source.notes = '\n'.join(note_lines)
                updated = True

            # save changes if any were made
            if updated:
                source.save()

            # return the existing source for creating a footnote
            return source

        # existing source not found;create a new one!
        source = Source.objects.create(
            source_type=self.source_types[src_type],
            title=title,
            url=url, volume=volume,
            year=year,
            notes='\n'.join(
                ['Created from PGPID %s' % document.id] +
                note_lines))

        # associate language if specified
        if language:
            lang = SourceLanguage.objects.get(name=language)
            source.languages.add(lang)
        # associate authors
        self.add_source_authors(source, authors)

        # todo: return notes for footnote location?
        return source

    def add_source_authors(self, source, authors):
        # add authors, preserving listed order
        for i, author in enumerate(authors, 1):
            source.authorship_set.create(creator=author, sort_order=i)
