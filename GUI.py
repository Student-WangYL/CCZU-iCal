import tkinter as tk
from tkinter import messagebox
import sys
import requests
from lxml import etree
import datetime
import time
import re
import uuid
import os
from icalendar import Calendar, Event, Alarm
from typing import Optional
from conf_classTime import class_time_config
import platform

def loginCookie(
    user: str, passwd: str
) -> dict:  # 定义函数，传入学号和密码，返回Cookies
    session = requests.session()
    url = "http://jwcas.cczu.edu.cn/login"

    # 获取随机信息
    try:
        html = session.get(url, headers=headers)
        html.raise_for_status()
        html.encoding = html.apparent_encoding
        html = html.text
    except Exception:  # 如果获取失败，退出程序
        # print("从登录页获取随机信息失败")
        sys.exit(0)

    # 初始化字符串，使其可用于xpath的函数
    html = etree.HTML(html)
    # 获取随机数据的名称和值
    # Type of gName, gValue: list
    gName = html.xpath('//input[@type="hidden"]/@name')  # 获取随机信息的name
    gValue = html.xpath('//input[@type="hidden"]/@value')  # 获取随机信息的value
    gAll = {}  # 创建字典，用于存储随机信息
    for i in range(3):  # 将随机信息存入字典
        gAll[gName[i]] = gValue[i]  # 将随机信息的name和value存入字典

    # 发送数据
    data = {
        "username": user,
        "password": passwd,
        "warn": "true",
        "lt": gAll["lt"],
        "execution": gAll["execution"],
        "_eventId": gAll["_eventId"],
    }

    # 官方登录
    sc = session.post(url, headers=headers, data=data)
    if not sc.cookies.get_dict():
        messagebox.showerror("错误", "用户名或密码错误，请检查重试")
        sys.exit(0)

    # 拦截跳转链接
    try:
        tmp = session.get(
            "http://jwcas.cczu.edu.cn/login?service=http://219.230.159.132/login7_jwgl.aspx",
            headers=headers,
        )
        tmp_html = etree.HTML(tmp.text)
        Rurl = tmp_html.xpath("//a[@href and text()]/@href")[0]
    except Exception:
        messagebox.showerror("错误", "获取跳转链接失败")
        sys.exit(0)

    # 从DirectPage获取我们需要的Cookie
    try:
        tmp2 = session.get(Rurl, headers=headers)
    except Exception:
        messagebox.showerror("错误", "获取实用Cookies失败")
        sys.exit(0)

    # 提取cookie字典并返回它。
    return tmp2.cookies.get_dict()

# 定义函数，传入学号和密码，返回Cookies

# 定义函数，传入Cookies，返回课表


def getDom(cookies: dict) -> Optional[str]:
    url = "http://219.230.159.132/web_jxrw/cx_kb_xsgrkb.aspx"

    try:
        rep = requests.get(url, headers=headers, cookies=cookies)
        rep.raise_for_status()
        return rep.text
    except requests.exceptions.HTTPError:  # If get the status code - 500
        return None


def classHandler(text):
    # 结构文本
    textDom = etree.HTML(text)
    tables = textDom.xpath("//div/table")
    tableup, tabledown = tables[1], tables[2]
    # 提取所有课程名
    classNameList = tableup.xpath(
        './tr[@class="dg1-item"]/td[position()=2]/text()')
    # 从表格中提取课程信息
    classmatrix = [
        tr.xpath("./td[position()>1]/text()")
        for tr in tabledown.xpath("tr[position()>1]")
    ]
    classmatrixT = [each for each in zip(*classmatrix)]
    oeDict = {"单": 1, "双": 2}
    courseInfo = dict()
    courseList = dict()
    global courseInfoRes

    # day: 一周中的某一天 / courses: 一天内的所有课程

    for day, courses in enumerate(classmatrixT):
        for course_time, course_cb in enumerate(courses):
            course_list = list(filter(None, course_cb.split("/")))
            targetlen = len(course_list)
            index = 0
            while index < targetlen:
                course = course_list[index]
                if course != "\xa0":  # 检查课程是否为空
                    id = uuid.uuid3(uuid.NAMESPACE_DNS, course + str(day)).hex
                    if not course_time or id not in courseInfo.keys():
                        nl = list(
                            filter(lambda x: course.startswith(x), classNameList))
                        if not nl:  # 如果没有匹配的课程名称
                            if index < targetlen - 1:  # 如果不是最后一个元素
                                # 将当前课程和下一个课程合并，并替换下一个课程
                                course_list[index +
                                            1] = f"{course}/{course_list[index + 1]}"
                                index += 1  # 跳过下一个元素
                                continue
                            else:
                                raise ValueError("无法正确解析课程名称")
                        # 如果找到匹配的课程名称
                        assert len(nl) == 1, "多个课程名称匹配，无法正确解析"
                        classname = nl[0]
                        course = course.replace(classname, "").strip()
                        res = re.match(
                            r"(\S+)? *([单双]?) *((\d+-\d+,?)+)", course)
                        assert res, "Course information parsing exception"
                        info = {
                            "classname": classname,
                            "classtime": [course_time + 1],
                            "day": day + 1,
                            "week": list(filter(None, res.group(3).split(","))),
                            "oe": oeDict.get(res.group(2), 3),
                            "classroom": [res.group(1)],
                        }
                        courseInfo[id] = info
                    elif id in courseInfo.keys():
                        courseInfo[id]["classtime"].append(course_time + 1)
                index += 1

    # 合并同一课程的不同上课时间
    for course in courseInfo.values():
        purecourse = {key: value for key,
                      value in course.items() if key != "classroom"}
        # 如果课程已经存在，将教室信息添加到课程信息中
        if str(purecourse) in courseList:
            courseList[str(purecourse)]["classroom"].append(
                course["classroom"][0])
        # 如果课程不存在，将课程信息添加到课程列表中
        else:
            courseList[str(purecourse)] = course
    # 将课程列表转换为课程信息列表
    courseInfoRes = [course for course in courseList.values()]


# 定义函数，传入课表，返回ics文件


def setReminder(reminder):
    # reminder: 课前提醒时间
    global timeReminder
    reminder = 15 if reminder == "" else reminder
    # 将分钟转换为ics文件中的时间格式
    time_tuple = re.match(
        r"(([\d ]+) days, )*(\d+):(\d+):(\d+)",
        str(datetime.timedelta(minutes=int(reminder))),
    ).groups()[1:]
    # 将时间格式转换为ics文件中的时间格式
    time_map = map(lambda x: x if x else "0", time_tuple)
    timeReminder = "-P{}DT{}H{}M{}S".format(*list(time_map))


# 定义函数，传入课表，返回ics文件

# 为了方便打包
'''def setClassTime():
    # 从配置文件中读取上课时间
    data = []
    with open("conf_classTime.json", "r") as f:
        data = json.load(f)
    global classTimeList
    classTimeList = data["classTime"]
    print("上课时间配置成功")'''


def setClassTime():
    # 直接从导入的模块中读取上课时间
    global classTimeList
    classTimeList = class_time_config["classTime"]
    



def save(string):
    f = open("class.ics", "wb")
    f.write(string.encode("utf-8"))
    f.close()


# 定义类，传入课表，返回ics文件


class ICal(object):
    def __init__(self, firstWeekDate, schedule, courseInfo):
        self.firstWeekDate = firstWeekDate
        self.schedule = schedule
        self.courseInfo = courseInfo

    # 传入字符串日期，返回类实例

    @classmethod
    def withStrDate(cls, strdate, *args):
        firstWeekDate = time.strptime(strdate, "%Y%m%d")
        return cls(firstWeekDate, *args)

    # 传入时间戳，返回类实例

    def handler(self, info):
        weekday = info["day"]
        oe = info["oe"]
        firstDate = datetime.datetime.fromtimestamp(
            int(time.mktime(self.firstWeekDate))
        )
        info["daylist"] = list()
        # 将课程的周数转换为日期
        for weeks in info["week"]:
            startWeek, endWeek = map(int, weeks.split("-"))
            startDate, endDate = (
                firstDate
                + datetime.timedelta(days=(float((startWeek - 1) * 7) + weekday - 1)),
                firstDate
                + datetime.timedelta(days=(float((endWeek - 1) * 7) + weekday - 1)),
            )

            # 如果课程为单周或双周，将其添加到课程信息中
            while True:
                if (
                    oe == 3
                    or (oe == 1)
                    and (startWeek % 2 == 1)
                    or (oe == 2)
                    and (startWeek % 2 == 0)
                ):
                    info["daylist"].append(startDate.strftime("%Y%m%d"))
                startDate = startDate + datetime.timedelta(days=7.0)
                startWeek = startWeek + 1
                if startDate > endDate:
                    break
        return info

    # 传入课表，返回ics文件

    def to_ical(self):
        prop = {
            "PRODID": "-//Google Inc//Google Calendar 70.9054//EN",
            "VERSION": "2.0",
            "CALSCALE": "GREGORIAN",
            "METHOD": "PUBLISH",
            "X-WR-CALNAME": "课程表",
            "X-WR-TIMEZONE": "Asia/Shanghai",
        }
        # 将课表信息添加到ics文件中
        cal = Calendar()
        for key, value in prop.items():
            cal.add(key, value)

        courseInfo = map(self.handler, self.courseInfo)
        for course in courseInfo:
            startTime = self.schedule[course["classtime"][0] - 1]["startTime"]
            endTime = self.schedule[course["classtime"][-1] - 1]["endTime"]
            classroom = list(filter(None, course["classroom"]))
            createTime = datetime.datetime.now()
            for day in course["daylist"]:
                sub_prop = {
                    "CREATED": createTime,
                    "SUMMARY": "{0} | {1}".format(
                        course["classname"], "/".join(classroom)
                    ),
                    "UID": uuid.uuid4().hex + "@google.com",
                    "DTSTART": datetime.datetime.strptime(
                        day + startTime, "%Y%m%d%H%M"
                    ),
                    "DTEND": datetime.datetime.strptime(day + endTime, "%Y%m%d%H%M"),
                    "DTSTAMP": createTime,
                    "LAST-MODIFIED": createTime,
                    "SEQUENCE": "0",
                    "TRANSP": "OPAQUE",
                    "X-APPLE-TRAVEL-ADVISORY-BEHAVIOR": "AUTOMATIC",
                }
                # 如果课前提醒时间不为空，将其添加到课程信息中
                sub_prop_alarm = {
                    "ACTION": "DISPLAY",
                    "DESCRIPTION": "This is an event reminder",
                    "TRIGGER": timeReminder,
                }
                event = Event()
                for key, value in sub_prop.items():
                    event.add(key, value)
                alarm = Alarm()
                for key, value in sub_prop_alarm.items():
                    alarm[key] = value
                event.add_component(alarm)
                cal.add_component(event)

        # 每周信息
        fweek = datetime.datetime.fromtimestamp(
            int(time.mktime(self.firstWeekDate))) - datetime.timedelta(days=1.0)
        createTime = datetime.datetime.now()
        for _ in range(18):
            sub_prop = {
                "CREATED": createTime,
                "SUMMARY": "学期第 {} 周".format(_ + 1),
                "UID": uuid.uuid4().hex + "@google.com",
                "DTSTART": fweek.date(),
                "DTEND": (fweek + datetime.timedelta(days=7.0)).date(),
                "DTSTAMP": createTime,
                "LAST-MODIFIED": createTime,
                "SEQUENCE": "0",
                "TRANSP": "OPAQUE",
                "X-APPLE-TRAVEL-ADVISORY-BEHAVIOR": "AUTOMATIC",
            }
            fweek += datetime.timedelta(days=7.0)
            event = Event()
            for key, value in sub_prop.items():
                event.add(key, value)
            cal.add_component(event)

        return (
            bytes.decode(
                cal.to_ical(), encoding="utf-8").replace("\r\n", "\n").strip()
        )

def login():
    student_number = entry_student_number.get()
    password = entry_password.get()
    reminder_time = entry_reminder.get()
    first_week_date = entry_first_week_date.get()

    # 输入验证
    if not student_number or not password:
        messagebox.showerror("错误", "请输入学号和密码。")
        return
    if not reminder_time.isdigit():
        messagebox.showerror("错误", "提醒时间请输入数字。")
        return
    if len(first_week_date) != 8 or not first_week_date.isdigit():
        messagebox.showerror("错误", "请输入正确格式的日期（如：20240226）。")
        return

    # 这里调用功能代码中的函数
    try:
        cookies = loginCookie(student_number, password)  # 使用用户输入的学号和密码

        dom = getDom(cookies)
        if not dom:
            messagebox.showerror("错误", "获取课表失败，请重试。")
            return
        else:
            print("获取课表成功")

        classHandler(dom)
        # 配置课表时间
        setClassTime()
        # 配置第一周日期
        print("SetFirstWeekDate:", first_week_date)
        # 配置课前提醒
        setReminder(reminder_time)
        
        iCal = ICal.withStrDate(first_week_date, classTimeList, courseInfoRes)   
        ics_file_path = get_save_path()
        with open(ics_file_path, "w", encoding="utf-8") as f:
            f.write(iCal.to_ical())
        messagebox.showinfo("成功", "课程表已成功生成！")
    except Exception as e:
        messagebox.showerror("错误", f"发生错误：{e}")

# 根据操作系统获取保存路径
def get_save_path():
    system = platform.system()
    if system == "Windows":
        desktop_path = os.path.join(os.path.join(
            os.environ['USERPROFILE']), 'Desktop')
        return os.path.join(desktop_path, "class.ics")
    elif system == "Darwin":  # macOS
        return os.path.join(os.path.join(os.path.expanduser('~')), 'Downloads', "class.ics")
    elif system == "Linux":
        return os.path.join(os.path.join(os.path.expanduser('~')), 'Downloads', "class.ics")
    else:
        raise OSError("Unsupported operating system")


# 在代码中调用 get_save_path() 函数来获取保存路径
ics_file_path = get_save_path()
# 主函数
if __name__ == "__main__":
    firstWeekDate = None
    classTimeList = None
    courseInfoRes = None
    timeReminder = None

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/72.0.3626.121 Safari/537.36"
    }
    # GUI 代码
# 登录按钮的回调函数
# 创建主窗口

root = tk.Tk()
root.title("课程表助手")

# 创建一个登录字段的框架
frame_login = tk.Frame(root)
frame_login.pack(padx=10, pady=10)

# 学号输入
label_student_number = tk.Label(frame_login, text="学号：")
label_student_number.grid(row=0, column=0, sticky="e")
entry_student_number = tk.Entry(frame_login)
entry_student_number.grid(row=0, column=1)

# 密码输入
label_password = tk.Label(frame_login, text="密码：")
label_password.grid(row=1, column=0, sticky="e")
entry_password = tk.Entry(frame_login, show="*")
entry_password.grid(row=1, column=1)

# 课前提醒时间输入
label_reminder = tk.Label(frame_login, text="提醒时间（分钟）：")
label_reminder.grid(row=2, column=0, sticky="e")
entry_reminder = tk.Entry(frame_login)
entry_reminder.grid(row=2, column=1)

# 第一周星期一日期输入
label_first_week_date = tk.Label(frame_login, text="第一周星期一（如20240226）：")
label_first_week_date.grid(row=3, column=0, sticky="e")
entry_first_week_date = tk.Entry(frame_login)
entry_first_week_date.grid(row=3, column=1)



# GUI 组件创建代码
# 登录按钮
button_login = tk.Button(frame_login, text="提交", command=login)
button_login.grid(row=4, column=0, columnspan=2, pady=5)

# 主循环
root.mainloop()
