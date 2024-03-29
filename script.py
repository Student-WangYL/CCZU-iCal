import json
import sys
import datetime
import time
import re
import uuid
import requests
from icalendar import Calendar, Event, Alarm
from random import Random
from lxml import etree


def loginCookie(user: str, passwd: str) -> dict:
    session = requests.session()
    url = "http://jwcas.cczu.edu.cn/login"

    # Get the random data to login
    try:
        html = session.get(url, headers=headers)
        html.raise_for_status()
        html.encoding = html.apparent_encoding
        html = html.text
    except:
        print("Failed to pick up details of LoginPage.")
        sys.exit(0)

    # Initialize the string, which makes it available to the function of xpath
    html = etree.HTML(html)
    # Get the name and value of random data
    # Type of gName, gValue: list
    gName = html.xpath('//input[@type="hidden"]/@name')
    gValue = html.xpath('//input[@type="hidden"]/@value')

    gAll = {}
    for i in range(3):
        gAll[gName[i]] = gValue[i]

    # Post data
    data = {
        'username': user,
        'password': passwd,
        'warn': 'true',
        'lt': gAll['lt'],
        'execution': gAll['execution'],
        '_eventId': gAll['_eventId']
    }

    # Official Login
    sc = session.post(url, headers=headers, data=data)
    if not sc.cookies.get_dict():
        print("Failed to Login, please check the username and password.")
        sys.exit(0)

    # Intercept jump link
    try:
        tmp = session.get(
            'http://jwcas.cczu.edu.cn/login?service=http://219.230.159.132/login7_jwgl.aspx', headers=headers)
        tmp_html = etree.HTML(tmp.text)
        Rurl = tmp_html.xpath('//a[@href and text()]/@href')[0]
    except:
        print("Failed to pick up JumpPage's URL.")
        sys.exit(0)

    # Get Cookies we need from DirectPage
    try:
        tmp2 = session.get(Rurl, headers=headers)
    except:
        print("Failed to pick up Cookies of DirectPage.")
        sys.exit(0)

    # Extract the cookies dictionary and return it.
    print("Getting Cookies Successfully.")
    return tmp2.cookies.get_dict()


def getDom(cookies: dict) -> list:
    url = "http://219.230.159.132/web_jxrw/cx_kb_xsgrkb.aspx"

    try:
        rep = requests.get(url, headers=headers, cookies=cookies)
        rep.raise_for_status()
        return rep.text
    except requests.exceptions.HTTPError:  # If get the status code - 500
        return None


def classHandler(text):
    # structure text
    textDom = etree.HTML(text)
    tables = textDom.xpath('//div/table')
    tableup, tabledown = tables[1], tables[2]
    # extract all class names
    classNameList = tableup.xpath(
        './tr[@class="dg1-item"]/td[position()=2]/text()')
    # extract class info of from the table
    classmatrix = [tr.xpath('./td[position()>1]/text()')
                   for tr in tabledown.xpath('tr[position()>1]')]
    classmatrixT = [each for each in zip(*classmatrix)]
    oeDict = {'单': 1, '双': 2}
    courseInfo = dict()
    courseList = dict()
    global courseInfoRes

    # day: day of week / courses: all courses in a day
    for day, courses in enumerate(classmatrixT):
        # time: the rank of lesson / course_cb: one item in table cell
        for time, course_cb in enumerate(courses):
            course_list = list(filter(None, course_cb.split('/')))
            for course in course_list:
                id = uuid.uuid3(uuid.NAMESPACE_DNS, course+str(day)).hex
                if course != '\xa0' and (not time or id not in courseInfo.keys()):
                    nl = list(
                        filter(lambda x: course.startswith(x), classNameList))
                    assert len(
                        nl) == 1, "Unable to resolve course name correctly"
                    classname = nl[0]
                    course = course.replace(classname, '').strip()
                    res = re.match(
                        r'(\w+)? *([单双]?) *((\d+-\d+,?)+)', course)
                    assert res, "Course information parsing abnormal"
                    info = {
                        'classname': classname,
                        'classtime': [time+1],
                        'day': day+1,
                        'week': list(filter(None, res.group(3).split(','))),
                        'oe': oeDict.get(res.group(2), 3),
                        'classroom': [res.group(1)],
                    }
                    courseInfo[id] = info
                elif course != '\xa0' and id in courseInfo.keys():
                    courseInfo[id]['classtime'].append(time+1)

    for course in courseInfo.values():
        purecourse = {key: value for key,
                      value in course.items() if key != "classroom"}
        if str(purecourse) in courseList:
            courseList[str(purecourse)]["classroom"].append(
                course["classroom"][0])
        else:
            courseList[str(purecourse)] = course

    courseInfoRes = [course for course in courseList.values()]
    print("Class Schedule Processed Successfully")


def setReminder(reminder):
    global timeReminder
    reminder = 15 if reminder == '' else reminder
    time_tuple = re.match(r"(([\d ]+) days, )*(\d+):(\d+):(\d+)",
                          str(datetime.timedelta(minutes=int(reminder)))).groups()[1:]
    time_map = map(lambda x: x if x else "0", time_tuple)
    timeReminder = "-P{}DT{}H{}M{}S".format(*list(time_map))
    print("SetReminder:", timeReminder)


def setClassTime():
    data = []
    with open('conf_classTime.json', 'r') as f:
        data = json.load(f)
    global classTimeList
    classTimeList = data["classTime"]
    print("Setting ClassTime Successfully.")


def save(string):
    f = open("class.ics", 'wb')
    f.write(string.encode("utf-8"))
    f.close()


class ICal(object):
    def __init__(self, firstWeekDate, schedule, courseInfo):
        self.firstWeekDate = firstWeekDate
        self.schedule = schedule
        self.courseInfo = courseInfo

    @classmethod
    def withStrDate(cls, strdate, *args):
        firstWeekDate = time.strptime(strdate, "%Y%m%d")
        return cls(firstWeekDate, *args)

    def handler(self, info):
        weekday = info["day"]
        oe = info["oe"]
        firstDate = datetime.datetime.fromtimestamp(
            int(time.mktime(self.firstWeekDate)))
        info['daylist'] = list()

        for weeks in info["week"]:
            startWeek, endWeek = map(int, weeks.split('-'))
            startDate, endDate = firstDate + datetime.timedelta(days=(float(
                (startWeek - 1) * 7) + weekday - 1)), firstDate + datetime.timedelta(days=(float((endWeek - 1) * 7) + weekday - 1))

            while True:
                if (
                    oe == 3 
                    or (oe == 1) 
                    and (startWeek % 2 == 1) 
                    or (oe == 2) 
                    and (startWeek % 2 == 0)
                    ):
                    info['daylist'].append(startDate.strftime("%Y%m%d"))
                startDate = startDate + datetime.timedelta(days=7.0)
                startWeek = startWeek + 1
                if (startDate > endDate):
                    break
        return info

    def to_ical(self):
        prop = {
            'PRODID': '-//Google Inc//Google Calendar 70.9054//EN',
            'VERSION': '2.0',
            'CALSCALE': 'GREGORIAN',
            'METHOD': 'PUBLISH',
            'X-WR-CALNAME': '课程表',
            'X-WR-TIMEZONE': 'Asia/Shanghai'
        }
        cal = Calendar()
        for key, value in prop.items():
            cal.add(key, value)

        courseInfo = map(self.handler, self.courseInfo)
        for course in courseInfo:
            startTime = self.schedule[course['classtime'][0]-1]['startTime']
            endTime = self.schedule[course['classtime'][-1]-1]['endTime']
            classroom = list(filter(None, course["classroom"]))
            createTime = datetime.datetime.now()
            for day in course['daylist']:
                sub_prop = {
                    'CREATED': createTime,
                    'SUMMARY': "{0} | {1}".format(course['classname'], '/'.join(classroom)),
                    'UID': uuid.uuid4().hex + '@google.com',
                    'DTSTART': datetime.datetime.strptime(day+startTime, '%Y%m%d%H%M'),
                    'DTEND': datetime.datetime.strptime(day+endTime, '%Y%m%d%H%M'),
                    'DTSTAMP': createTime,
                    'LAST-MODIFIED': createTime,
                    'SEQUENCE': '0',
                    'TRANSP': 'OPAQUE',
                    'X-APPLE-TRAVEL-ADVISORY-BEHAVIOR': 'AUTOMATIC'
                }
                sub_prop_alarm = {
                    'ACTION': 'DISPLAY',
                    'DESCRIPTION': 'This is an event reminder',
                    'TRIGGER': timeReminder
                }
                event = Event()
                for key, value in sub_prop.items():
                    event.add(key, value)
                alarm = Alarm()
                for key, value in sub_prop_alarm.items():
                    alarm[key] = value
                event.add_component(alarm)
                cal.add_component(event)

        # weekly info
        fweek = datetime.date.fromtimestamp(
            int(time.mktime(self.firstWeekDate))) - datetime.timedelta(days=1.0)
        createTime = datetime.datetime.now()
        for _ in range(18):
            sub_prop = {
                'CREATED': createTime,
                'SUMMARY': "学期第 {} 周".format(_ + 1),
                'UID': uuid.uuid4().hex + '@google.com',
                'DTSTART': fweek,
                'DTEND': fweek + datetime.timedelta(days=7.0),
                'DTSTAMP': createTime,
                'LAST-MODIFIED': createTime,
                'SEQUENCE': '0',
                'TRANSP': 'OPAQUE',
                'X-APPLE-TRAVEL-ADVISORY-BEHAVIOR': 'AUTOMATIC'
            }
            fweek += datetime.timedelta(days=7.0)
            event = Event()
            for key, value in sub_prop.items():
                event.add(key, value)
            cal.add_component(event)

        return bytes.decode(cal.to_ical(), encoding='utf-8').replace('\r\n', '\n').strip()


if __name__ == "__main__":
    firstWeekDate = None
    classTimeList = None
    courseInfoRes = None
    timeReminder = None

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/72.0.3626.121 Safari/537.36'}

    userInfo = input(
        'Please input your Username and Password to Login(Separated by Space in one line): ').split()
    try:
        print("Getting Cookies...")
        gCookie = loginCookie(userInfo[0], userInfo[1])  # Type: Dict
    except:
        print('Meet the error when try to Login, please try again.')
        sys.exit(0)

    # gCookie = {'ASP.NET_SessionId': 'rc11ki45x4545w3njnbpfbqw'}

    print("Getting Class Schedule...")
    textDom = getDom(gCookie)
    if not textDom:
        print('Meet the error when try to get RawClass, please try again.')
        sys.exit(0)
    else:
        print("Getting Class Schedule Successfully")

    print("Processing Class Schedule...")
    classHandler(textDom)

    print("Setting ClassTime...")
    setClassTime()

    firstWeekDate = input(
        'Please set the Monday date of the first week (eg 20160905): ')  # Date of the first week of Monday
    print("Setting The First WeekDate...")
    print("SetFirstWeekDate:", firstWeekDate)

    reminder = input(
        'The reminder function is being configured, please set the reminder time in minutes (default 15): ')
    print("Setting Reminder...")
    setReminder(reminder)

    print("Creating and Saving ics File...")
    iCal = ICal.withStrDate(firstWeekDate, classTimeList, courseInfoRes)
    with open("./class.ics", "w", encoding="utf-8") as f:
        f.write(iCal.to_ical())
    print("File Saved Successfully")
