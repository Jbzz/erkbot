import sys
import socket
import string
import pickle
import os.path
import time
import thread
import threading

DEBUGIRC = False
DENIED = "Access Denied."
PREFIX = ">>"
modified = time.strftime('%y%m%d.%H%M%S',time.localtime(os.path.getmtime(__file__)))
VERSIONREPLY = "Erkbot v"+modified+" Tizen"

gameModes = {}
gameModes["random"] = {}
gameModes["random"]["help"] = "3-N players, 30-40% scum, 15-20% random roles"
gameModes["random"]["mods"] = {}
gameModes["random"]["mods"]["scum_min"] = .3
gameModes["random"]["mods"]["scum_max"] = .4
gameModes["random"]["mods"]["role_min"] = .15
gameModes["random"]["mods"]["role_max"] = .2

class erkBotClass(object):
    #HOST = "irc.freenode.net"
    HOST = "mainstreetlogo.com"
    PORT = 6667
    NICK = "Erkbot"
    IDENT = "Erkbot"
    REALNAME = "Erk Bot"
    CHANNEL = "#erk"
    owners = ["hatesandwich","Tizen"]
    myName = ""
    chanops = {}
    games = {}
    sendqueue = []
    ircsettings = {}
    def __init__(self):
        self.DICFILE = "erk.dic"
        self.dic = {}
        self.sendChecker = Manager()
        self.sendChecker.add_operation(self.checkSend,.75)
        if os.path.exists(self.DICFILE) and os.path.isfile(self.DICFILE) and (os.path.getsize(self.DICFILE) > 0):
            tmpfile = open(self.DICFILE,'r')
            self.dic = pickle.load(tmpfile)
            tmpfile.close
            print "Dictionary file loaded!"
        else:
            tmpfile = open(self.DICFILE,'w+')
            pickle.dump(self.dic,tmpfile)
            tmpfile.close
            print "Dictionary file initialized!"
    def disconnect(self):
        self.s.close()
    def connect(self):
        self.s = socket.socket()
        self.s.connect((self.HOST, self.PORT))
        self.s.send("NICK %s\r\n" % self.NICK)
        self.s.send("USER %s %s xxx :%s\r\n" % (self.IDENT, self.HOST, self.REALNAME))
    def readbuf(self, amnt):
        return self.s.recv(amnt)
    def checkSend(self):
        checkGameStatus(self)
        if len(self.sendqueue) > 0:
            self.s.send(self.sendqueue[0])
            del self.sendqueue[0]
    def send(self, message):
        self.sendqueue.append(message)
    def updateOp(self, nick, newnick):
        for chan in self.chanops.iterkeys():
            if nick in self.chanops[chan]:
                self.chanops[chan].remove(nick)
                self.chanops[chan].append(newnick)
    def delOp(self, nick, channel = False):
        if not channel:
            for testChannel in self.chanops.iterkeys():
                if nick in self.chanops[testChannel]:
                    self.chanops[testChannel].remove(nick)
        elif self.chanops.has_key(channel) and nick in self.chanops[channel]:
            self.chanops[channel].remove(nick)
    def addOp(self, nick, channel):
        alreadyOp = False
        if self.chanops.has_key(channel) and nick in self.chanops[channel]:
            alreadyOp = True
        else:
            alreadyOp = False
        if not alreadyOp:
            if not self.chanops.has_key(channel):
                self.chanops[channel] = []
            self.chanops[channel].append(nick)
    def isOp(self, nick, channel = False):
        if not channel:
            for testChannel in self.chanops.iterkeys():
                if nick in self.chanops[testChannel]:
                    return True
            return False
        if self.chanops.has_key(channel) and nick in self.chanops[channel]:
            return True
        return False

class Operation(threading._Timer):
    def __init__(self, *args, **kwargs):
        threading._Timer.__init__(self, *args, **kwargs)
        self.setDaemon(True)
    def run(self):
        while True:
            self.finished.clear()
            self.finished.wait(self.interval)
            if not self.finished.isSet():
                self.function(*self.args, **self.kwargs)
            else:
                return
            self.finished.set()

class Manager(object):
    ops = []
    def add_operation(self, operation, interval, args=[], kwargs={}):
        op = Operation(interval, operation, args, kwargs)
        self.ops.append(op)
        thread.start_new_thread(op.run, ())

    def stop(self):
        for op in self.ops:
            op.cancel()
        self._event.set()

def ircInput(line, b):
    SUPRESS = False
    word = string.split(line)
           
    if (word[1] == "001"): # irc connection established
        b.myName = word[2]
        print "connected as "+word[2]+"!"
        b.send("JOIN "+b.CHANNEL+"\r\n")
    elif (word[1] == "005"): # irc server settings
        SUPRESS = True
        settings = string.split(string.join(string.split(string.join(word[3:],' '),':')[:-1],':'))
        for setting in settings:
            x = string.split(setting,'=')
            if len(x) == 2:
                b.ircsettings[x[0]] = x[1]
            else:
                b.ircsettings[x[0]] = True
    elif (word[1] == "NICK"): # nick change
        SUPRESS = True
        longHost = hostBreakup(word[0])
        nick, ident, domain = longHost
        newnick = word[2][1:]
        b.updateOp(nick,newnick)
        if nick == b.myName:
            b.myName = newnick
        print "*** "+nick+" is now known as "+newnick
    elif (word[1] == "353"): # nick list on channel join
        nicks = line.split(':')[2]
        nick = string.split(nicks)
        for checkOp in nick:
            if checkOp[0] == "@":
                b.addOp(checkOp[1:],word[4])
    elif (word[1] == "JOIN"): # user joins channel
        SUPRESS = True
        longHost = hostBreakup(word[0])
        nick, ident, domain = longHost
        chan = word[2][1:]
        print "*** "+nick+"@"+chan+" joins"

        gname = string.join(string.split(chan,'_')[1:],'_')
        if b.games.has_key(gname):
            if nick != b.myName and b.games[gname]["status"] == 1:
                b.games[gname]["players"][nick] = {}
                privMsg(b,chan,nick+" has joined the game. "+str(playerCount(b,gname))+" total")
    elif (word[1] == "PART"): # user parts channel
        SUPRESS = True
        longHost = hostBreakup(word[0])
        nick, ident, domain = longHost
        chan = word[2]
        print "*** "+nick+"@"+chan+" parts ("+string.join(word[3:],' ')[1:]+")"
        b.delOp(nick,chan)

        gname = string.join(string.split(chan,'_')[1:],'_')
        delPlayer(b,nick,gname)
        
    elif (word[1] == "QUIT"): # user quits
        SUPRESS = True
        longHost = hostBreakup(word[0])
        nick, ident, domain = longHost
        print "*** "+nick+" quits ("+string.join(word[2:],' ')[1:]+")"
        b.delOp(nick)
        delPlayer(b,nick)
    elif (word[1] == "MODE"): # mode change
        SUPRESS = True
        longHost = hostBreakup(word[0])
        nick, ident, domain = longHost
        print "*** "+nick+"@"+word[2]+" sets mode "+string.join(word[3:],' ')
        mode = 0
        param = 3
        for char in word[3]:
            if char == "+":
                mode = 1
            elif char == "-":
                mode = 2
            else:
                param += 1
                if char == "o" and mode == 1:
                    b.addOp(word[param],word[2])
                elif char == "o" and mode == 2:
                    b.delOp(word[param],word[2])
    elif (word[1] == "PRIVMSG"): # user messages a channel or erk directly
        SUPRESS = True
        longHost = hostBreakup(word[0])
        nick, ident, domain = longHost
        chan = word[2]
        replyto = nick if b.myName == chan else chan
        text = string.join(word[3:],' ')[1:]
        print "<"+nick+"@"+chan+"> " + text # display to console

        words = string.split(text)
        if (text == "who are you?"):
            privMsg(b,replyto,b.myName+".")
        elif text == chr(1)+"VERSION"+chr(1):
            sendNotice(b,nick,chr(1)+"VERSION "+VERSIONREPLY+chr(1))
        elif (words[0][0:len(PREFIX)] == PREFIX): # command prefix
            command = words[0][len(PREFIX):]
            params = string.join(words[1:],' ')
            doCommand(b, longHost, chan, command, params)
            
    elif (word[0] == "PING"): # connection keepalive
        SUPRESS = True
        b.send("PONG %s\r\n" % word[1])
        # print "PING? PONG!"
        
    if DEBUGIRC and not SUPRESS:
        print line
def doCommand(b, longHost, chan, command, params = ""):
    nick, ident, domain = longHost
    replyto = nick if b.myName == chan else chan

    if command == "listops":
        if b.chanops.has_key(replyto):
            privMsg(b,replyto,"ops: "+string.join(b.chanops[replyto]))
        elif not replyto == chan:
            privMsg(b,replyto,"This command must be used in a channel.")
        else:
            privMsg(b,replyto,"No ops for "+replyto)
    elif command == "list":
        if len(b.games) > 0:
            for gname in b.games.iterkeys():
                gowner = b.games[gname]["owner"]
                gchan = b.games[gname]["channel"]
                gstatus = b.games[gname]["status"]
                gstyle = b.games[gname]["style"]
                gstatus2 = ""
                if gstatus == 0:
                    gstatus2 = "creating"
                elif gstatus == 1:
                    gstatus2 = "waiting for players"
                else:
                    gstatus2 = "unknown ["+str(gstatus)+"]"
                privMsg(b,replyto,gchan+" ("+gstyle+", "+gstatus2+") by "+gowner+" ["+str(playerCount(b,gname))+" players]")
        else:
            privMsg(b,replyto,"There are no games.")
    elif command == "restart" and (nick in b.owners) and b.isOp(nick,chan):
        privMsg(b,replyto,"Restarting....")
        b.send("QUIT :Restarting.\r\n")
        while len(b.sendqueue) > 0:
            pass
        time.sleep(1)        
        b.disconnect()
        print "Reconnecting...",
        b.connect()
    elif command == "die" and (nick in b.owners) and b.isOp(nick,chan):
        privMsg(b,replyto,"Shutting down....")
        b.send("QUIT :Shutting down.\r\n")
        while len(b.sendqueue) > 0:
            pass
        time.sleep(1)
        b.disconnect()
        sys.exit()
    elif command == "exec" and (nick in b.owners) and b.isOp(nick,chan):
        print "> "+params
        b.send(params+"\r\n")
    elif command == "create":
        gname = ""
        if params != "":
            sParams = string.split(params)
            gname = string.split(sParams[0],',')[0]
            try:
                gstyle = sParams[1]
            except:
                gstyle = "random"
        if gname == "":
            gname = "game"+str(len(b.games) + 1)
            gstyle = "random"
        gchan = b.CHANNEL+"_"+gname
        if b.games.has_key(gname):
            privMsg(b,replyto,"That game ("+gname+") has already been created.")
        elif int(b.ircsettings['CHANNELLEN']) < len(gchan):
            privMsg(b,replyto,"Cannot create game, name too long.")
        elif gstyle not in gameModes:
            privMsg(b,replyto,"Unknown game style: "+gstyle)
        else:
            b.games[gname] = {}
            b.games[gname]["owner"] = nick
            b.games[gname]["channel"] = gchan
            b.games[gname]["status"] = 0
            b.games[gname]["style"] = gstyle
            b.games[gname]["expire"] = time.time() + 10
            b.games[gname]["reqop"] = False
            b.games[gname]["players"] = {}
            b.send("JOIN "+gchan+"\r\n")
    elif command == "settings":
        try:
            if params == "":
                privMsg(b,replyto,"Settings: "+string.join(b.ircsettings))
            elif b.ircsettings.has_key(params):
                privMsg(b,replyto,params+" setting: "+str(b.ircsettings[params]))
            else:
                privMsg(b,replyto,"Invalid setting!")
        except:
            privMsg(b,replyto,"Oops, exception in command == settings! "+sys.exc_info()[0])
    elif command == "destroy":
        try:
            if params != "":
                deschan = b.CHANNEL + "_" + string.split(params)[0]
            else:
                deschan = chan
            dodestroy = ""
            for gname in b.games.iterkeys():
                if b.games[gname]["channel"] == deschan:
                    if b.games[gname]["owner"] == nick:
                        dodestroy = gname
                    else:
                        privMsg(b,replyto,"You must be the game owner to destroy that game.")
            if dodestroy != "":
                b.send("PART "+b.games[dodestroy]["channel"]+"\r\n")
                del b.games[dodestroy]
                privMsg(b,replyto,"Game destroyed.")
            else:
                privMsg(b,replyto,"Game does not exist. ("+deschan+")")
        except:
            print "Unexpected DESTROY error:", sys.exc_info()[0]
                    
def checkGameStatus(b):
    delgames = []
    if len(b.games) > 0:
        for gname in b.games.iterkeys():
            if b.games[gname]["status"] == 0:
                if b.isOp(b.myName,b.games[gname]["channel"]):
                    b.games[gname]["status"] = 1
                    privMsg(b,b.CHANNEL,"Game "+gname+" created. Join "+b.games[gname]["channel"]+" to play.")
                elif b.games[gname]["expire"] <= time.time():
                    privMsg(b,b.CHANNEL,"Could not create game "+gname)
                    b.send("PART "+b.games[gname]["channel"]+"\r\n")
                    delgames.append(gname)
                elif b.games[gname]["expire"] + 5 >= time.time() and not b.games[gname]["reqop"]:
                    privMsg(b,b.games[gname]["channel"],"I require operator status to create this game.")
                    b.games[gname]["reqop"] = True
        for gname in delgames:
            del b.games[gname]
def playerCount(b,gname):
    if b.games.has_key(gname):
        return len(b.games[gname]["players"])
    return 0
def delPlayer(b,nick,gnameAlpha = False):
    keepGoing = True
    gname = ""
    while keepGoing:
        keepGoing = False
        if gnameAlpha is False:
            for gtest in b.games:
                if b.games[gtest]["players"].has_key(nick):
                    gname = gtest
                    keepGoing = True
        else:
            gname = gnameAlpha
        if b.games.has_key(gname):
            if b.games[gname]["players"].has_key(nick):
                if b.games[gname]["owner"] == nick:
                    privMsg(b,b.games[gname]["channel"],nick+" has left the game. Game destroyed.")
                    doCommand(b,[nick,nick,nick],b.games[gname]["channel"],"destroy")
                else:
                    del b.games[gname]["players"][nick]
                    privMsg(b,b.games[gname]["channel"],nick+" has left the game. "+str(playerCount(b,gname))+" remaining.")
def privMsg(b,target,message):
    print "<"+b.myName+"@"+target+"> "+message
    b.send("PRIVMSG "+target+" :"+message+"\r\n")
def sendNotice(b,target,message):
    print "-"+b.myName+"@"+target+"- "+message
    b.send("NOTICE "+target+" :"+message+"\r\n")
def hostBreakup(longHost):
    host = longHost[1:].split("@")
    if len(host) == 1:
        return [host[0],host[0],host[0]]
    domain = host[1]
    nickident = host[0].split("!")
    ident = nickident[1]
    nick = nickident[0]
    return [nick,ident,domain]

def reloadInit(b):
    pass
