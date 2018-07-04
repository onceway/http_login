#!/usr/local/bin/python
#encoding=utf-8
# auto login script
# for python version 2.5 and upper
# Update log
# 06.29 增加验证码OCR识别，需要tesseract软件的支持
# 2018
# 06.09 修改详细信息提取公式，以符合新的页面格式
# 2015
# 01.31 使用smtplib中的TLS登录方式，去掉对chilkat库的依赖
#       恢复对中文的支持
# 01.16 修改邮件登录方式为TLS
#       该版本需要配合第三方python库chilkat使用，需要python2.5以上版本
#       另外此版本邮件标题和邮件内容不支持中文，中文会乱码
# 2012
# 09.14 增加密码base64加密，命令行运行此脚本带密码明文参数，可获得加密后的字符串;
#       增加show_detail配置选项
# 04.15 Record连接增加了一个参数，从界面解析并加上此参数
# 03.30 清除了界面新增的表头个人信息的显示
# 2011
# 10.15 增加了仅失败时发送邮件提醒
# 09.25 修改了一处可能引起重复Record的隐患
# 09.12 修改了login重试次数错误的bug
# 08.31 添加节假日扩展和自动判断周末;改为紧凑式日志结构
# 08.30 添加同步写文件
# 08.16 增加email通知
# 08.09 增加log模式
# 2010

import os, sys, platform
import string, time, socket, random
import urllib, urllib2, cookielib, smtplib
import base64
try:
	import Image
except ImportError:
	import PIL.Image as Image


# url settings
url_base = 'http://192.168.2.53'                                # 用于计算登陆验证页面地址
url_index = 'http://192.168.2.53/'                              # 主页面
url_login = 'http://192.168.2.53/login.jsp'                     # 登陆验证页面(已不用)
url_code = 'http://192.168.2.53/imageRandeCode'                 # 验证码
url_show = 'http://192.168.2.53/attendance.jsp'                 # 查询页面
url_record = 'http://192.168.2.53/record.jsp'                   # Record页面
# user settings
yourname = ''
username = ''
password = ''
# ocr app
ocr_app = 'tesseract'                                           # ocr识别app
ocr_tmp = '/tmp'                                                # ocr临时文件目录
# time settings
timeout = 5                                                     # socket超时时间
retry_tm = 20                                                   # 操作重试等待时间
e_ts = 5                                                        # Record最大重试次数，超出该次数则重新登录
retry_total = 5                                                 # 最大错误次数，超出则退出脚本
# delay settings (second)
delay_start = 0                                                 # 脚本开始等待时间段
delay_end = 600
wait_login_st = 3                                               # 登陆等待时间段
wait_login_ed = 10
wait_record_st = 2                                              # Record等待时间段
wait_record_ed = 5
# log file
uselog = 1                                                      # 是否使用log文件
show_detail = 0                                                 # 是否打印个人信息
logfile = '/var/h-log'                                          # log文件路径
# holiday
holiday_file = '/var/h-holiday'                                 # Holiday配置文件
# mail settings
mail_enable = 1                                                 # 启用email提示
mail_only_failed = 0                                            # 仅在失败时发送
mail_server = '202.107.117.23:587'                              # smtp服务器地址
mail_to = '%s@neusoft.com' % base64.b64decode(username)         # 收件人
mail_from = '%s@neusoft.com' % base64.b64decode(username)       # 发件人
mail_title_ok = '[Notify] Morning'                              # 成功时email的标题
mail_title_failed = '[Notify] Evening'                          # 失败时email的标题
mail_content_ok = '您好，提醒您及时登陆 http://kq.neusoft.com/ 进行上下班打卡，以免影响考勤结果。祝您度过愉快的一天。'
                                                                # 成功时email的内容
mail_content_failed = mail_content_ok                           # 失败时email的内容
# debug
debug_on = 0                                                    # 开启时无视“脚本开始等待时间”，不进行Record操作，不使用日志模式
test_mail = 0                                                   # 邮件调试模式，开启后跳过前部代码直接从发送邮件部分执行

# 刷新文件写入
def uplog(logfd):
        if not uselog :
                return
        logfd.flush()
        os.fsync(logfd.fileno())

# 节假日扩展
def workingday(confile) :
        weekday = time.strftime("%w")
        today = time.strftime("%m%d")
        if weekday == "6" or weekday == "7" or weekday == "0" :
                iswd = 0
        else :
                iswd = 1
        try :
                f = open(confile, 'r')
                days = f.readlines()
        except Exception :
                return iswd
        for day in days :
                if day[0] == "#" :
                        continue
                if today == day[0:4] :
                        iswd = string.atoi(day[5])
                        if iswd == 1 :
                                print "Holiday find today is a working day."
                        else :
                                print "Holiday find today is not a working day."
                        break
        f.close()
        return iswd

# code regnized
def regnize_code(cookie, suffix):
	jfif_file = ocr_tmp + 'code_' + suffix + '.jfif'
	tif_file = ocr_tmp + 'code_' + suffix + '.tif'
	txt_name = ocr_tmp + 'code_' + suffix
	txt_file = txt_name + '.txt'
	try:
		opener=urllib2.build_opener(urllib2.HTTPCookieProcessor(cookie))
		u=opener.open(url_code)
		content =  u.read()
		f = open(jfif_file, 'w')
		f.write(content)
		f.close()
	except Exception, e:
		print e
		if os.path.exists(jfif_file):
			os.remove(jfif_file)
		return None
	im = Image.open(jfif_file)
	im = im.convert('L')
	im.save(tif_file)
	os.system(ocr_app + ' ' + tif_file + ' ' + txt_name + ' -l num')
	code_file = open(txt_file, "r")
	code = code_file.read().replace(' ','').replace('\n', '')
	code_file.close()
	if os.path.exists(jfif_file):
		os.remove(jfif_file)
	if os.path.exists(tif_file):
		os.remove(tif_file)
	if os.path.exists(txt_file):
		os.remove(txt_file)
	return code

# Encode and print password
def do_option(arglen, args):
        if arglen < 2: 
                return
        i = 1;
        while i < arglen:
                print base64.b64encode(args[i])
                i = i + 1
        sys.exit()

if __name__ == '__main__':
        do_option(len(sys.argv), sys.argv)

        err_tms = 0
        login_err = 0
        retimes = 0
        user_tag = ''
        pwd_tag = ''
        keyid = ''
        neuid = ''
        neuid_val = ''
        neuat = 'neusoft_attendance_online'
        login_url = ''
        r_times = 0
        record_ok = 0
        dc_yourname = base64.b64decode(yourname);
        dc_username = base64.b64decode(username);
        dc_password = base64.b64decode(password);

        if debug_on :
                uselog = 0
# 重定向输出到log文件
        if uselog :
                try:
                        cmd = 'touch %s' % (logfile)
                        os.system(cmd)
                        log_file = open(logfile, 'a')
                        sys.stdout = log_file
                        sys.stderr = log_file
                except Exception, e:
                        print e
        else :
                log_file = sys.stdout

        print "< %s >" % time.strftime("%Y-%m-%d %H:%M:%S")
# 判断是否为工作日
        if not workingday(holiday_file) :
                print "Holiday! script quit !"
                print "< %s >\n" % time.strftime("%Y-%m-%d %H:%M:%S")
                sys.exit()

        sec = random.randint(delay_start, delay_end)
        print 'Wait for', sec, 'seconds.'
        if not debug_on:
                uplog(log_file)
                time.sleep(sec)

        cj = cookielib.CookieJar()
        socket.setdefaulttimeout(timeout)

        while 1:

                err_tms = 0
                if test_mail :
                        break
                        
                try:
                        opener=urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))
# 获取用户名和密码的 tag name
                        u=opener.open(url_index)
                        content = u.readlines()

                        line = content[28]
                        login_url = line[line.find('"') + 1:]
                        login_url = login_url[0:login_url.find('"')]
                        
                        line = content[32]
                        keyid = line[line.find('"KEY') + 1:]
                        keyid = keyid[0:keyid.find('"')]
                        
                        line = content[33]
                        neuid = line[line.find('"ID') + 1:]
                        neuid = neuid[0:neuid.find('"')]

                        line = content[42]
                        user_tag = line[line.find('"ID') + 1:]
                        user_tag = user_tag[0:user_tag.find('"')]
                        
                        line = content[43]
                        pwd_tag = line[line.find('"KEY') + 1:]
                        pwd_tag = pwd_tag[0:pwd_tag.find('"')]

                        line = content[46]
                        code_tag = line[line.find('"YZM') + 1:]
                        code_tag = code_tag[0:code_tag.find('"')]

                        url_login = '%s%s' % (url_base, login_url)

			code = regnize_code(cj, username)
			if code == None or len(code) != 4:
				print 'Regnize code failed, code is %s. Retry in %d seconds.' % (code, retry_tm)
				retimes = retimes + 1
				if retimes == retry_total:
					print "Too many error, script quit."
					break
				uplog(log_file)
				time.sleep(retry_tm)
				continue
			else:
				print 'Code is', code

			#print user_tag, dc_username
			#print pwd_tag, dc_password
			#print code_tag, code
			#print keyid
			#print neuid
			#print url_base
			#print login_url
			#print url_login

# 发送登陆请求
                        body = (('login', 'true'), (user_tag, dc_username), (pwd_tag, dc_password), (code_tag, code), (neuat, ''), (keyid, ''), ('neusoft_key', neuid))
                        req=urllib2.Request(url_login, urllib.urlencode(body))
# 登录延迟时间
                        sec = random.randint(wait_login_st, wait_login_ed)
                        print 'Wait for', sec, 'seconds to send login.'
                        uplog(log_file)
                        time.sleep(sec)

                        u=opener.open(req)
                        content = u.read()

                except Exception, e:
                        print e
                        print "Retry in", retry_tm, "seconds."
                        retimes = retimes + 1
                        if retimes == retry_total:
                                print "Too many error, script quit."
                                break
                        uplog(log_file)
                        time.sleep(retry_tm)
                        continue
# 登陆成功判断
                if 'attendanceForm' not in content:
                        print "Login Failed !\nRetry in", retry_tm, "seconds."
                        uplog(log_file)
                        login_err = login_err + 1
                        if login_err == retry_total:
                                print "Login Failed for too many times !\n"
                                break
                        time.sleep(retry_tm)
                        continue

                pos=content.find('input')
                record_param1=content[pos+26:content[pos+26:].find('"')+pos+26]
                record_value1=content[pos+48:content[pos+48:].find('"')+pos+48]

                print "Login Successfull !"
# 申请Record
                while 1:
                        try:
# Record延迟时间
                                if record_ok == 1 :
                                        print 'Record OK, don\'t send record.'
                                        break;

                                body = {record_param1 : record_value1}
                                req=urllib2.Request(url_record, urllib.urlencode(body))

                                sec = random.randint(wait_record_st, wait_record_ed)
                                print 'Wait for', sec, 'seconds to send record.'
                                uplog(log_file)
                                time.sleep(sec)

                                if not debug_on :
                                        u=opener.open(req)
                                record_ok = 1

                        except Exception, e:
                                print e
                                print "Recorder Failed !\nRetry in", retry_tm, "seconds."
                                err_tms = err_tms + 1
                                if err_tms == e_ts:
                                        break
                                uplog(log_file)
                                time.sleep(retry_tm)
                                continue

                        break
                
                if err_tms == e_ts:
                        print "Too many error, relogin in", retry_tm, "seconds."
                        uplog(log_file)
                        time.sleep(retry_tm)
                        continue
# 获取Record记录
                try:
                        u=opener.open(url_show)
                        content = u.readlines()
                        if show_detail:
                                print "Today's record is :"
                        for line in content:
                                if '<td>' in line:
                                        if show_detail:
                                                print line.strip('\t\n\r<>tdivclasex"/ =-')
                                        if dc_yourname in line:
                                                r_times = r_times + 1
                except Exception, e:
                        print e

                if record_ok == 1 :
                        print 'Record OK !'
                else :
                        print 'Record Failed !'

                break

# 发送提醒email
        if mail_enable :
                if not(mail_only_failed and record_ok) :
                        try :
                                smtp = smtplib.SMTP()
#                               smtp.set_debuglevel(True)
                                smtp.connect(mail_server)
                                smtp.starttls()
                                smtp.login(dc_username, dc_password)
                                if record_ok :
                                        msg = "To: %s\r\nFrom: %s\r\nSubject: %d_%s\r\n\r\n %s\r\n" % \
                                                        (mail_to, mail_from, r_times, mail_title_ok, mail_content_ok)
                                else :
                                        msg = "To: %s\r\nFrom: %s\r\nSubject: %s\r\n\r\n %s\r\n" % \
                                                        (mail_to, mail_from, mail_title_failed, mail_content_failed)
                                smtp.sendmail(mail_from, mail_to, msg)
                                smtp.quit()
                                print "Notify e-mail sent OK."
                        except Exception, e:
                                print e
                                print "Notify e-mail sent Failed !"


        print "< %s >\n" % time.strftime("%Y-%m-%d %H:%M:%S")

