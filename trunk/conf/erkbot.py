import sys
import socket
import string
import time
import erkSystem
import pickle
import os.path
import thread
import threading
from erkSystem import erkBotClass

ERKSYSTEMFILE = "erkSystem.py"
watermark = open(ERKSYSTEMFILE).readlines()
reloadTime = time.time()

readbuffer = ""

b = erkBotClass()
print "Connecting...",
b.connect()

while True:
    readbuffer = readbuffer + b.readbuf(1024)
    temp = string.split(readbuffer, "\n")
    readbuffer = temp.pop( )

    if reloadTime <= time.time():
        reloadTime = time.time() + 1
        checkWatermark = open(ERKSYSTEMFILE).readlines()
        if checkWatermark != watermark:
            reload(erkSystem)
            watermark = checkWatermark
            erkSystem.reloadInit(b)
            print "* reloaded "+ERKSYSTEMFILE
        if os.path.exists(b.DICFILE) and os.path.isfile(b.DICFILE) and (os.path.getsize(b.DICFILE) > 0):
            tmpfile = open(b.DICFILE,'r')
            dicMark = pickle.load(tmpfile)
            tmpfile.close
            if dicMark != b.dic:
                tmpfile = open(b.DICFILE,'w+')
                pickle.dump(b.dic,tmpfile)
                tmpfile.close
                print "Dictionary file updated!"
        elif dic != {}:
            tmpfile = open(b.DICFILE,'w+')
            pickle.dump(b.dic,tmpfile)
            tmpfile.close
            print "Dictionary file updated!"

    for line in temp:
        line = string.rstrip(line)
        erkSystem.ircInput(line, b)

