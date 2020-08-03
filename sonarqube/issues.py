#!/usr/local/bin/python3
'''

    Abstraction of the SonarQube "issue" concept

'''
import sys
import re
import datetime
import json
import requests
import sonarqube.env as env
import sonarqube.sqobject as sq
import sonarqube.utilities as util

OPTIONS_ISSUES_SEARCH = ['additionalFields', 'asc', 'assigned', 'assignees', 'authors', 'componentKeys',
                         'createdAfter', 'createdAt', 'createdBefore', 'createdInLast', 'directories',
                         'facetMode', 'facets', 'fileUuids',
                         'issues', 'languages', 'onComponentOnly', 'p', 'ps', 'resolutions', 'resolved',
                         'rules', 's', 'severities', 'sinceLeakPeriod', 'statuses', 'tags', 'types']

MAX_ISSUE_SEARCH = 10000
ISSUE_SEARCH_API = 'issues/search'

class ApiError(Exception):
    pass


class UnknownIssueError(ApiError):
    pass

class TooManyIssuesError(Exception):
    def __init__(self, nbr_issues, message):
        super().__init__()
        self.nbr_issues = nbr_issues
        self.message = message

class IssueComments:
    def __init__(self, json_data):
        self.json = json_data

    def sort(self):
        sorted_comment = dict()
        for comment in self.json:
            sorted_comment[comment['createdAt']] = ('comment', comment)
        return sorted_comment

    def size(self):
        return len(self.json)

    def to_string(self):
        """Dumps the object in a string"""
        return json.dumps(self.json, sort_keys=True, indent=3, separators=(',', ': '))

class Issue(sq.SqObject):
    def __init__(self, key, sqenv):
        super().__init__(key, sqenv)
        self.url = None
        self.json = None
        self.severity = None
        self.type = None
        self.author = None
        self.assignee = None
        self.status = None
        self.resolution = None
        self.rule = None
        self.project = None
        self.language = None
        self.changelog = None
        self.comments = None
        self.line = None
        self.component = None
        self.message = None
        self.debt = None
        self.sonarqube = None
        self.creation_date = None
        self.modification_date = None
        self.hash = None

    def __str__(self):
        return "Key:{0} - Type:{1} - Severity:{2} - File/Line:{3}/{4} - Rule:{5}".format( \
            self.key, self.type, self.severity, self.component, self.line, self.rule)

    def to_string(self):
        """Dumps the object in a string"""
        return json.dumps(self.json, sort_keys=True, indent=3, separators=(',', ': '))

    def get_url(self):
        if self.url is None:
            self.url = '{0}/project/issues?id={1}&issues={2}'.format(self.env.get_url(), self.component, self.key)
        return self.url

    def __feed__(self, jsondata):
        self.json = jsondata
        util.json_dump_debug(jsondata, "ISSUE = ")
        self.id = jsondata['key']
        self.type = jsondata['type']
        if self.type != 'SECURITY_HOTSPOT':
            self.severity = jsondata['severity']
        self.author = jsondata['author']
        self.assignee = None # json['assignee']
        self.status = jsondata['status']
        try:
            self.line = jsondata['line']
        except KeyError:
            self.line = None

        self.resolution = None # json['resolution']
        self.rule = jsondata['rule']
        self.project = jsondata['project']
        self.language = None
        self.changelog = None
        self.creation_date = jsondata['creationDate']
        self.modification_date = jsondata['updateDate']

        self.changelog = None
        self.component = jsondata['component']
        try:
            self.hash = jsondata['hash']
        except KeyError:
            self.hash = None
        try:
            self.message = jsondata['message']
        except KeyError:
            self.message = None
        try:
            self.debt = jsondata['debt']
        except KeyError:
            self.debt = None

    def read(self):
        params = dict(issues=self.key, additionalFields='_all')
        resp = self.get(ISSUE_SEARCH_API, params)
        self.__feed__(resp.issues[0])

    def get_changelog(self, force_api = False):
        if (force_api or self.changelog is None):
            resp = self.get('issues/changelog', {'issue':self.key, 'format':'json'})
            data = json.loads(resp.text)
            # util.json_dump_debug(data['changelog'], "Issue Changelog = ")
            self.changelog = []
            for l in data['changelog']:
                d = diff_to_changelog(l['diffs'])
                self.changelog.append({'date':l['creationDate'], 'event':d['event'], 'value':d['value']})
        return self.changelog

    def has_changelog(self):
        util.logger.debug('Issue %s had %d changelog', self.key, len(self.get_changelog()))
        return len(self.get_changelog()) > 0

    def get_comments(self):
        if 'comments' not in self.json:
            self.comments = []
        elif self.comments is None:
            self.comments = []
            for c in self.json['comments']:
                self.comments.append({'date':c['createdAt'], 'event':'comment', 'value':c['markdown']})
        return self.comments

    def get_all_events(self, is_sorted = True):
        events = self.get_changelog()
        util.logger.debug('Get all events: Issue %s has %d changelog', self.key, len(events))
        comments = self.get_comments()
        util.logger.debug('Get all events: Issue %s has %d comments', self.key, len(comments))
        for c in comments:
            events.append(c)
        if not is_sorted:
            return events
        bydate = {}
        for e in events:
            bydate[e['date']] = e
        return bydate

    def has_comments(self):
        comments = self.get_comments()
        return len(comments) > 0

    def has_changelog_or_comments(self):
        return self.has_changelog() or self.has_comments()

    def add_comment(self, comment):
        util.logger.debug("Adding comment %s to issue %s", comment, self.key)
        return self.post('issues/add_comment', {'issue':self.key, 'text':comment})

    # def delete_comment(self, comment_id):

    # def edit_comment(self, comment_id, comment_str)

    def get_severity(self, force_api = False):
        if force_api or self.severity is None:
            self.read()
        return self.severity

    def set_severity(self, severity):
        """Sets severity"""
        util.logger.debug("Changing severity of issue %s from %s to %s", self.key, self.severity, severity)
        return self.post('issues/set_severity', {'issue':self.key, 'severity':severity})

    def assign(self, assignee):
        """Sets assignee"""
        util.logger.debug("Assigning issue %s to %s", self.key, assignee)
        return self.post('issues/assign', {'issue':self.key, 'assignee':assignee})

    def get_authors(self):
        """Gets authors from SCM"""

    def set_tags(self, tags):
        """Sets tags"""
        util.logger.debug("Setting tags %s to issue %s", tags, self.key)
        return self.post('issues/set_tags', {'issue':self.key, 'tags':tags})

    def get_tags(self):
        """Gets tags"""

    def set_type(self, new_type):
        """Sets type"""
        util.logger.debug("Changing type of issue %s from %s to %s", self.key, self.type, new_type)
        return self.post('issues/set_type', {'issue':self.key, 'type':new_type})

    def get_type(self):
        """Gets type"""

    def get_status(self):
        return self.status

    def has_been_marked_as_wont_fix(self):
        return self.__has_been_marked_as_statuses__(["WONTFIX"])


    def has_been_marked_as_false_positive(self):
        return self.__has_been_marked_as_statuses__(["FALSE-POSITIVE"])


    def __has_been_marked_as_statuses__(self, statuses):
        for log in self.get_changelog():
            for diff in log['diffs']:
                if diff["key"] != "resolution":
                    continue
                for status in statuses:
                    if diff["newValue"] == status:
                        return True
        return False

    def get_key(self):
        return self.key

    def __same_rule(self, another_issue):
        return self.rule == another_issue.rule

    def __same_hash(self, another_issue):
        return self.hash == another_issue.hash

    def __same_message(self, another_issue):
        return self.message == another_issue.message

    def __same_debt(self, another_issue):
        return self.debt == another_issue.debt

    def same_general_attributes(self, another_issue):
        return self.__same_rule(another_issue) and self.__same_hash(another_issue) and \
               self.__same_message(another_issue)

    def is_vulnerability(self):
        return self.type == 'VULNERABILITY'

    def is_hotspot(self):
        return self.type == 'SECURITY_HOTSPOT'

    def is_bug(self):
        return self.type == 'BUG'

    def is_code_smell(self):
        return self.type == 'CODE_SMELL'

    def is_security_issue(self):
        return self.is_vulnerability() or self.is_hotspot()

    def __identical_security_issues(self, another_issue):
        return self.is_security_issue() and another_issue.is_security_issue()

    def identical_to(self, another_issue, ignore_component = False):
        if not self.same_general_attributes(another_issue) or \
            (self.component != another_issue.component and not ignore_component):
            # util.logger.debug("Issue %s and %s are different on general attributes", self.key, another_issue.key)
            return False
        # Hotspots carry no debt,so you can only check debt equality if issues
        # are not hotspots
        if not self.is_hotspot() and not another_issue.is_hotspot() and self.debt != another_issue.debt:
            util.logger.info("Issue %s and %s are different on debt", self.key, another_issue.key)
            return False
        util.logger.info("Issue %s and %s are identical", self.get_url(), another_issue.get_url())
        return True

    def identical_to_except_comp(self, another_issue):
        return self.identical_to(another_issue, ignore_component = True)

    def match(self, another_issue):
        util.logger.debug("Comparing 2 issues: %s and %s", str(self), str(another_issue))
        if self.rule != another_issue.rule or self.hash != another_issue.hash:
            match_level = 0
        else:
            match_level = 1
            if self.component != another_issue.component:
                match_level -= 0.1
            if self.message != another_issue.message:
                match_level -= 0.1
            if self.debt != another_issue.debt:
                match_level -= 0.1
        util.logger.debug("Match level %3.0f%%\n", (match_level * 100))
        return match_level

    def do_transition(self, transition):
        return self.post('issues/do_transition', {'issue':self.key, 'transition':transition})

    def reopen(self):
        util.logger.debug("Reopening issue %s", self.id)
        return self.do_transition('reopen')

    def mark_as_false_positive(self):
        util.logger.debug("Marking issue %s as false positive", self.key)
        return self.do_transition('falsepositive')

    def mark_as_wont_fix(self):
        util.logger.debug("Marking issue %s as won't fix", self.key)
        return self.do_transition('wontfix')

    def mark_as_reviewed(self):
        if self.is_hotspot():
            util.logger.debug("Marking hotspot %s as reviewed", self.key)
            return self.do_transition('resolveasreviewed')
        elif self.is_vulnerability():
            util.logger.debug("Marking vulnerability %s as won't fix in replacement of 'reviewed'", self.key)
            ret = self.do_transition('wontfix')
            self.add_comment("Vulnerability marked as won't fix to replace hotspot 'reviewed' status")
            return ret

        util.logger.debug("Issue %s is neither a hotspot nor a vulnerability, cannot mark as reviewed", self.key)
        return False

    def to_csv(self):
        # id,project,rule,type,severity,status,creation,modification,project,file,line,debt,message
        debt = 0
        if self.debt is not None:
            m = re.search(r'(\d+)kd', self.debt)
            kdays = int(m.group(1)) if m else 0
            m = re.search(r'(\d+)d', self.debt)
            days = int(m.group(1)) if m else 0
            m = re.search(r'(\d+)h', self.debt)
            hours = int(m.group(1)) if m else 0
            m = re.search(r'(\d+)min', self.debt)
            minutes = int(m.group(1)) if m else 0
            debt = ((kdays * 1000 + days) * 24 + hours) * 60 + minutes
        cdate = re.sub(r"T.*", "", self.creation_date)
        ctime = re.sub(r".*T", "", self.creation_date)
        # Strip timezone
        ctime = re.sub(r"\+.*", "", ctime)
        mdate = re.sub(r"T.*", "", self.modification_date)
        mtime = re.sub(r".*T", "", self.modification_date)
        # Strip timezone
        mtime = re.sub(r"\+.*", "", mtime)
        msg = re.sub('"','""', self.message)
        line = '-' if self.line is None else self.line
        import sonarqube.projects as projects
        return ';'.join([str(x) for x in [self.key, self.rule, self.type, self.severity, self.status,
                                          cdate, ctime, mdate, mtime, self.project,
                                          projects.get_name(self.project, self.env), self.component, line,
                                          debt, '"'+msg+'"']])


#------------------------------- Static methods --------------------------------------
def check_fp_transition(diffs):
    util.logger.debug("----------------- DIFFS     -----------------")
    return diffs[0]['key'] == "resolution" and diffs[0]["newValue"] == "FIXED" and \
           (diffs[1]["oldValue"] == "FALSE-POSITIVE" or diffs[1]["oldValue"] == "WONTFIX")

def sort_comments(comments):
    sorted_comments = dict()
    for comment in comments:
        sorted_comments[comment['createdAt']] = ('comment', comment)
    return sorted_comments

def search(sqenv = None, **kwargs):
    params = get_issues_search_params(kwargs)
    resp = env.get(ISSUE_SEARCH_API, params=params, ctxt=sqenv)
    data = json.loads(resp.text)
    nbr_issues = data['paging']['total']
    util.logger.debug("Number of issues: %d", nbr_issues)
    page = data['paging']['pageIndex']
    nbr_pages = ((data['paging']['total']-1) // data['paging']['pageSize'])+1
    util.logger.debug("Page: %d/%d", data['paging']['pageIndex'], nbr_pages)
    all_issues = []
    for json_issue in data['issues']:
        issue = Issue(key = json_issue['key'], sqenv = sqenv)
        issue.__feed__(json_issue)
        all_issues = all_issues + [issue]
    return dict(page=page, pages=nbr_pages, total=nbr_issues, issues=all_issues)

def search_all_issues(sqenv = None, **kwargs):
    util.logger.info('searching issues for %s', str(kwargs))
    kwargs['ps'] = 500
    page = 1
    nbr_pages = 1
    issues = []
    while page <= nbr_pages and page <= 20:
        kwargs['p'] = page
        returned_data = search(sqenv = sqenv, **kwargs)
        issues = issues + returned_data['issues']
        #if returned_data['total'] > MAX_ISSUE_SEARCH and page == 20: NOSONAR
        #    raise TooManyIssuesError(returned_data['total'], \
        #          'Request found %d issues which is more than the maximum allowed %d' % \
        #          (returned_data['total'], MAX_ISSUE_SEARCH) NOSONAR
        page = returned_data['page']
        nbr_pages = returned_data['pages']
        page = page + 1
        kwargs['p'] = page
    util.logger.debug ("Total number of issues: %d", len(issues))
    return issues

def get_facets(sqenv = None, facet = 'directories', **kwargs):
    kwargs['facets'] = facet
    kwargs['ps'] = 100
    params = get_issues_search_params(kwargs)
    resp = env.get(ISSUE_SEARCH_API, params=params, ctxt=sqenv)
    data = json.loads(resp.text)
    util.json_dump_debug(data, 'FACET')
    for f in data['facets']:
        if f['property'] == facet:
            return f['values']
    return []

def get_one_issue_date(sqenv=None, asc_sort='true', **kwargs):
    ''' Returns the date of one issue found '''
    kwtemp = kwargs.copy()
    kwtemp['s'] = 'CREATION_DATE'
    kwtemp['asc'] = asc_sort
    kwtemp['ps'] = 1
    try:
        returned_data = search(sqenv=sqenv, **kwtemp)
    except TooManyIssuesError:
        pass

    if returned_data['total'] == 0:
        return None
    else:
        return returned_data['issues'][0].creation_date

def get_oldest_issue(sqenv=None, **kwargs):
    ''' Returns the oldest date of all issues found '''
    return get_one_issue_date(sqenv=sqenv, asc_sort='true', **kwargs)

def get_newest_issue(sqenv=None, **kwargs):
    ''' Returns the newest date of all issues found '''
    return get_one_issue_date(sqenv=sqenv, asc_sort='false', **kwargs)

def get_number_of_issues(sqenv=None, **kwargs):
    ''' Returns number of issues of a search '''
    kwtemp = kwargs.copy()
    kwtemp['ps'] = 1
    returned_data = search(sqenv=sqenv, **kwtemp)
    util.logger.debug("Project %s has %d issues", kwargs['componentKeys'], returned_data['total'])
    return returned_data['total']

def search_project_daily_issues(key, day, sqenv=None, **kwargs):
    util.logger.debug("Searching daily issues for project %s on day %s", key, day)
    kw = kwargs.copy()
    kw['componentKeys'] = key
    if kwargs is None or 'severities' not in kwargs:
        severities = {'INFO','MINOR','MAJOR','CRITICAL','BLOCKER'}
    else:
        severities = re.split(',', kwargs['severities'])
    util.logger.debug("Severities = %s", str(severities))
    if kwargs is None or 'types' not in kwargs:
        types = {'CODE_SMELL','VULNERABILITY','BUG','SECURITY_HOTSPOT'}
    else:
        types = re.split(',', kwargs['types'])
    util.logger.debug("Types = %s", str(types))
    kw['createdAfter'] = day
    kw['createdBefore'] = day
    issues = []
    for severity in severities:
        kw['severities'] = severity
        for issue_type in types:
            kw['types'] = issue_type
            issues = issues + search_all_issues(sqenv=sqenv, **kw)
    util.logger.info("%d daily issues for project key %s on %s", len(issues), key, day)
    return issues

def search_project_issues(key, sqenv=None, **kwargs):
    kwargs['componentKeys'] = key
    oldest = get_oldest_issue(sqenv=sqenv, **kwargs)
    if oldest is None:
        return []
    startdate = datetime.datetime.strptime(oldest, '%Y-%m-%dT%H:%M:%S%z')
    enddate = datetime.datetime.strptime(get_newest_issue(sqenv=sqenv, **kwargs), '%Y-%m-%dT%H:%M:%S%z')

    nbr_issues = get_number_of_issues(sqenv=sqenv, **kwargs)
    days_slice = abs((enddate - startdate).days)+1
    if nbr_issues > MAX_ISSUE_SEARCH:
        days_slice = (MAX_ISSUE_SEARCH * days_slice) // (nbr_issues * 4)
    util.logger.debug("For project %s, slicing by %d days, between %s and %s", key, days_slice, startdate, enddate)

    issues = []
    window_start = startdate
    while window_start <= enddate:
        current_slice = days_slice
        sliced_enough = False
        while not sliced_enough:
            window_size = datetime.timedelta(days=current_slice)
            kwargs['createdAfter']  = util.format_date(window_start)
            window_stop = window_start + window_size
            kwargs['createdBefore'] = util.format_date(window_stop)
            found_issues = search_all_issues(sqenv=sqenv, **kwargs)
            if len(found_issues) < MAX_ISSUE_SEARCH:
                issues = issues + found_issues
                util.logger.debug("Got %d issue, OK, go to next window", len(found_issues))
                sliced_enough = True
                window_start = window_stop + datetime.timedelta(days=1)
            elif current_slice == 0:
                found_issues = search_project_daily_issues(key, kwargs['createdAfter'], sqenv, **kwargs)
                issues = issues + found_issues
                sliced_enough = True
                util.logger.error("Project key %s has many issues on %s, showing only the first %d",
                                  key, window_start, len(found_issues))
                window_start = window_stop + datetime.timedelta(days=1)
            else:
                sliced_enough = False
                current_slice = current_slice // 2
                util.logger.debug("Reslicing with a thinner slice of %d days", current_slice)

    util.logger.debug("For project %s, %d issues found", key, len(issues))
    return issues

def search_all_issues_unlimited(sqenv=None, **kwargs):
    import sonarqube.projects as projects
    if kwargs is None or 'componentKeys' not in kwargs:
        project_list = projects.search_all(endpoint=sqenv).keys()
    else:
        project_list= re.split(',', kwargs['componentKeys'])
    issues = []
    for project in project_list:
        issues = issues + projects.Project(key=project, sqenv=sqenv).get_all_issues()
    return issues

def apply_changelog(target_issue, source_issue):
    if target_issue.has_changelog():
        util.logger.error("Can't apply changelog to an issue that already has a changelog")
        return

    events = source_issue.get_all_events(True)

    if events is None or not events:
        util.logger.debug("Sibling %s has no changelog, no action taken", source_issue.key)
        return

    util.logger.info("Applying changelog of issue %s to issue %s", source_issue.key, target_issue.key)
    target_issue.add_comment("Synchronized from [this original issue]({0})".format(source_issue.get_url()))
    for d in sorted(events.iterkeys()):
        event = events[d]
        util.logger.debug("Verifying event %s", str(event))
        if is_event_a_severity_change(event):
            target_issue.set_severity(get_log_new_severity(event))
        elif is_event_a_type_change(event):
            target_issue.set_type(get_log_new_type(event))
        elif is_event_a_reopen(event):
            target_issue.reopen()
        elif is_event_a_resolve_as_fp(event):
            target_issue.mark_as_false_positive()
        elif is_event_a_resolve_as_wf(event):
            target_issue.mark_as_wont_fix()
        elif is_event_a_resolve_as_reviewed(event):
            target_issue.mark_as_reviewed()
        elif is_event_an_assignment(event):
            target_issue.assign(event['value'])
        elif is_event_a_tag_change(event):
            target_issue.set_tags(event['value'].replace(' ', ','))
        elif is_event_a_comment(event):
            target_issue.add_comment(event['value'])
        else:
            util.logger.error("Event %s can't be applied", str(event))


def get_log_date(log):
    return log['creationDate']

def is_log_a_closed_resolved_as(log, old_value):
    cond1 = False
    cond2 = False

    for diff in log['diffs']:
        if diff['key'] == 'resolution' and 'newValue' in diff and diff['newValue'] == 'FIXED' and \
            'oldValue' in diff and diff['oldValue'] == old_value:
            cond1 = True
        if diff['key'] == 'status' and 'newValue' in diff and diff['newValue'] == 'CLOSED' and \
            'oldValue' in diff and diff['oldValue'] == 'RESOLVED':
            cond2 = True
    return cond1 and cond2

def is_log_a_closed_wf(log):
    return is_log_a_closed_resolved_as(log, 'WONTFIX')

def is_log_a_comment(log):
    return True

def is_log_an_assign(log):
    return False

def is_log_a_tag(log):
    return False

def is_log_a_closed_fp(log):
    return is_log_a_closed_resolved_as(log, 'FALSE-POSITIVE')

def is_log_a_resolve_as(log, resolve_reason):
    cond1 = False
    cond2 = False
    for diff in log['diffs']:
        if diff['key'] == 'resolution' and 'newValue' in diff and diff['newValue'] == resolve_reason:
            cond1 = True
        if diff['key'] == 'status' and 'newValue' in diff and diff['newValue'] == 'RESOLVED':
            cond2 = True
    return cond1 and cond2

def is_log_a_reopen(log):
    cond1 = False
    cond2 = False
    for diff in log['diffs']:
        if diff['key'] == 'resolution':
            cond1 = True
        if diff['key'] == 'status' and 'newValue' in diff and diff['newValue'] == 'REOPENED':
            cond2 = True
    return cond1 and cond2

def is_log_a_reviewed(log):
    cond1 = False
    cond2 = False
    for diff in log['diffs']:
        if diff['key'] == 'resolution' and 'newValue' in diff and diff['newValue'] == 'FIXED':
            cond1 = True
        if diff['key'] == 'status' and 'newValue' in diff and diff['newValue'] == 'REVIEWED':
            cond2 = True
    return cond1 and cond2

def is_event_a_comment(event):
    return event['event'] == 'comment'

def is_event_an_assignment(event):
    return event['event'] == 'assign'

def is_event_a_resolve_as_fp(event):
    return event['event'] == 'transition' and event['value'] == 'falsepositive'

def is_event_a_resolve_as_wf(event):
    return event['event'] == 'transition' and event['value'] == 'wontfix'

def is_event_a_resolve_as_reviewed(event):
    return False

def is_event_a_severity_change(event):
    return event['event'] == 'severity'

def is_event_a_reopen(event):
    return event['event'] == 'transition' and event['value'] == 'reopen'

def is_event_a_type_change(event):
    return event['event'] == 'type'

def is_event_an_assignee_change(event):
    return event['event'] == 'assign'

def is_event_a_tag_change(event):
    return event['event'] == 'tags'

def get_log_assignee(event):
    return event['value']

def get_log_new_severity(event):
    return event['value']

def get_log_new_type(event):
    return event['value']

def get_log_new_tag(event):
    return event['value']

def identical_attributes(o1, o2, key_list):
    for key in key_list:
        if o1[key] != o2[key]:
            return False
    return True

def search_siblings(an_issue, issue_list, only_new_issues=True, check_component = False):
    siblings = []
    for issue in issue_list:
        if not issue.identical_to(an_issue, not check_component):
            continue
        if not only_new_issues or (only_new_issues and not issue.has_changelog()):
            # Add issue only if it has no change log, meaning it's brand new
            util.logger.debug("Adding issue %s to list", issue.get_url())
            siblings.append(issue)
    return siblings

def to_csv_header():
    return "# id;rule;type;severity;status;creation date;creation time;modification date;" + \
    "modification time;project key;project name;file;line;debt(min);message"

def get_issues_search_params(params):
    outparams = {'additionalFields':'comments'}
    for key in params:
        if params[key] is not None and key in OPTIONS_ISSUES_SEARCH:
            outparams[key] = params[key]
    return outparams

def resolution_diff_to_changelog(newval):
    if newval == 'FALSE-POSITIVE':
        return {'event':'transition', 'value':'falsepositive'}
    elif newval == 'WONTFIX':
        return {'event':'transition', 'value':'wontfix'}
    elif newval == 'FIXED':
        # TODO - Handle hotspots
        return {'event':'fixed', 'value': None}
    return {'event':'unknown', 'value': None}

def reopen_diff_to_changelog(oldval):
    if oldval == 'CONFIRMED':
        return {'event':'transition', 'value':'unconfirm'}
    return {'event':'transition', 'value':'reopen'}

def assignee_diff_to_changelog(d):
    if d['newValue'] in d:
        return {'event':'assign', 'value': d['newValue']}
    return {'event':'unassign', 'value':None}

def get_event_from_diff(diff):
    dkey = diff['key']
    dnewval = diff['newValue']
    event = None
    if dkey == 'severity' or dkey == 'type' or dkey == 'tags':
        event = {'event':dkey, 'value':dnewval}
    if dkey == 'resolution' and 'newValue' in diff:
        event =  resolution_diff_to_changelog(dnewval)
    if dkey == 'status' and 'newValue' in diff and dnewval == 'CONFIRMED':
        event =  {'event':'transition', 'value':'confirm'}
    if dkey == 'status' and 'newValue' in diff and dnewval == 'REOPENED':
        event =  reopen_diff_to_changelog(diff['oldValue'])
    if dkey == 'status' and 'newValue' in diff and dnewval == 'OPEN' and diff['oldValue'] == 'CLOSED':
        event =  {'event':'transition', 'value':'reopen'}
    if dkey == 'assignee':
        event =  assignee_diff_to_changelog(diff)
    if dkey == 'from_short_branch':
        event =  {'event':'merge', 'value':'{0} -> {1}'.format(diff['oldValue'],dnewval)}
    if dkey == 'effort':
        event = {'event':'effort', 'value':'{0} -> {1}'.format(diff['oldValue'],dnewval)}
    return event


def diff_to_changelog(diffs):
    for d in diffs:
        event = get_event_from_diff(d)
        if event is not None:
            return event

    # Not found anything
    return {'event':'unknown', 'value':None}
