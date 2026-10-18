"""Local startup progress window; service lifetime is independent of this window."""
import argparse
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk

parser=argparse.ArgumentParser()
parser.add_argument('--project', choices=['DeepTutor','OpenMAIC'], required=True)
parser.add_argument('--root', required=True)
args=parser.parse_args()
os.environ['LEARNING_SYSTEMS_ROOT']=args.root
import services
messages=queue.Queue()
window=tk.Tk()
window.title(args.project+' 启动')
window.geometry('520x170')
window.resizable(False,False)
window.option_add('*Font',('Microsoft YaHei UI',11))
label=ttk.Label(window,text='正在检查后台服务……',wraplength=475)
label.pack(padx=20,pady=(22,12),anchor='w')
bar=ttk.Progressbar(window,mode='indeterminate')
bar.pack(fill='x',padx=20)
bar.start(15)
ttk.Label(window,text='启动后可关闭网页，后台服务会继续运行。',font=('Microsoft YaHei UI',9)).pack(padx=20,pady=12,anchor='w')

def work():
    services.say=lambda text:messages.put(('status',text))
    try:
        services.manage('Start',args.project,open_page=True)
        messages.put(('done','已打开学习页面。'))
    except Exception as error:
        messages.put(('error',str(error)))

def pump():
    try:
        while True:
            kind,text=messages.get_nowait()
            label.configure(text=text)
            if kind=='done':
                bar.stop();window.after_idle(window.destroy);return
            if kind=='error':
                bar.stop()
                window.geometry('520x235')
                ttk.Button(window,text='打开日志目录',command=lambda:os.startfile(str(services.LOGS))).pack()
                return
    except queue.Empty:
        pass
    window.after(100,pump)

threading.Thread(target=work,daemon=True).start()
window.after(100,pump)
window.mainloop()
