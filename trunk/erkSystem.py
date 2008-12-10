import sys
import socket
import string
import pickle
import os.path
import time
import thread
import threading
import random

random.seed()

DEBUGIRC = False
DENIED = "Access Denied."
PREFIX = ">>"
modified = time.strftime('%y%m%d.%H%M%S',time.localtime(os.path.getmtime(__file__)))
VERSIONREPLY = "Erkbot v"+modified+" Tizen"
CREATE_EXPIRE = 60 # time to wait until bot has ops, before game creation is cancelled

#=== GAME MODES ===
modes = {}
modes["random"] = {}
modes["random"]["help"] = "3-N players, 25-34% scum, 10-16% random job or abilities"
modes["random"]["min"] = 3
modes["random"]["scum_min"] = 25.0
modes["random"]["scum_max"] = 34.0
modes["random"]["job_min"] = 10.0
modes["random"]["job_max"] = 16.0

#=== JOBS ===
jobs = {}

jobs["townie"] = {}
jobs["townie"]["title"] = "Vanilla Townie"
jobs["townie"]["abilities"] = ["vote"]
jobs["townie"]["limit"] = 999
jobs["townie"]["win"] = ["town"]
jobs["townie"]["help"] = "You are a Vanilla Townie. You can vote on daily lynchings and you win with the rest of the town."
jobs["townie"]["special"] = False

jobs["scum"] = {}
jobs["scum"]["title"] = "Mafia"
jobs["scum"]["abilities"] = ["kill","vote"]
jobs["scum"]["limit"] = 999
jobs["scum"]["win"] = ["mafia"]
jobs["scum"]["help"] = "You are a mafia member. You can designate 1 player each night to kill."
jobs["scum"]["special"] = False

jobs["doc"] = {}
jobs["doc"]["title"] = "Town Doctor"
jobs["doc"]["abilities"] = ["protect","vote"]
jobs["doc"]["limit"] = 1
jobs["doc"]["win"] = ["town"]
jobs["doc"]["help"] = "You are a town doctor. You can protect 1 player each night and prevent a mafia hit on them."
jobs["doc"]["special"] = True

jobs["sanecop"] = {}
jobs["sanecop"]["title"] = "Sane Police Officer"
jobs["sanecop"]["abilities"] = ["investigate","vote"]
jobs["sanecop"]["limit"] = 1
jobs["sanecop"]["win"] = ["town"]
jobs["sanecop"]["help"] = "You are a police officer. You can investigate 1 player each night to determine their faction."
jobs["sanecop"]["special"] = True

#=== SPECIALTIES ===
specs = {}

specs["rb"] = {}
specs["rb"]["title"] = "Roleblocker"
specs["rb"]["abilities"] = ["block"]
specs["rb"]["limit"] = 999
specs["rb"]["help"] = "Specialty: Roleblocker. You may block 1 player each night from performing their night actions."
specs["rb"]["faction"] = ["mafia"]

class erkBotClass(object):
    HOST = "irc.freenode.net"
    #HOST = "mainstreetlogo.com"
    PORT = 6667
    NICK = "Erkbot"
    IDENT = "Erkbot"
    REALNAME = "Erk Bot"
    CHANNEL = "#erk"
    owners = []
    ownerpassword = "ownerpass"
    myNick = ""
    channels = {}
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
        self.sendNickUser()
    def sendNickUser(self):
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
    def hasMode(self, nick, mode, chan = False):
        if not chan:
            for chan in self.channels.iterkeys():
                if self.channels[chan]["nicks"].has_key(nick) and mode in self.channels[chan]["nicks"][nick]:
                    return True
            return False
        if self.channels.has_key(chan) and self.channels[chan]["nicks"].has_key(nick) and mode in self.channels[chan]["nicks"][nick]:
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
        b.myNick = word[2]
        print "connected as "+word[2]+"!"
        b.send("JOIN "+b.CHANNEL+"\r\n")
        b.channels = {}
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
        if nick in b.owners:
            b.owners.remove(nick)
            b.owners.append(newnick)
        if nick == b.myNick:
            b.myNick = newnick
        oldnick = {}
        for chan in b.channels.iterkeys():
            if nick in b.channels[chan]["nicks"]:
                oldnick[chan] = nick
        if len(oldnick):
            for chan in oldnick.iterkeys():
                b.channels[chan]["nicks"][newnick] = b.channels[chan]["nicks"][oldnick[chan]]
                del b.channels[chan]["nicks"][oldnick[chan]]
        print "*** "+nick+" is now known as "+newnick
    elif (word[1] == "353"): # nick list on channel join
        nicks = line.split(':')[2]
        nick = string.split(nicks)
        chan = word[4]        
        prefixes = {}
        prefixIter = 0
        for prefix in string.split(b.ircsettings["PREFIX"],')')[1]:
            prefixIter += 1
            prefixes[prefix] = b.ircsettings["PREFIX"][prefixIter]
        if chan not in b.channels:
            b.channels[chan] = {}
            b.channels[chan]["nicks"] = {}
            b.channels[chan]["modes"] = []
        for checkMode in nick:
            prefixCheck = checkMode[0]
            prefix = ""
            if prefixes.has_key(prefixCheck):
                prefix = prefixes[prefixCheck]
                realNick = checkMode[1:]
            else:
                realNick = checkMode
            b.channels[chan]["nicks"][realNick] = []
            if not prefix == "":
                b.channels[chan]["nicks"][realNick].append(prefix)
    elif (word[1] == "433"): # nick already in use
        b.NICK += "_"
        b.sendNickUser()
    elif (word[1] == "JOIN"): # user joins channel
        SUPRESS = True
        longHost = hostBreakup(word[0])
        nick, ident, domain = longHost
        chan = word[2][1:]
        print "*** "+nick+"@"+chan+" joins"

        joinGame(b,chan,nick)
        if b.channels.has_key(chan):
            if not b.channels[chan]["nicks"].has_key(nick):
                b.channels[chan]["nicks"][nick] = []
    elif (word[1] == "PART"): # user parts channel
        SUPRESS = True
        longHost = hostBreakup(word[0])
        nick, ident, domain = longHost
        chan = word[2]
        print "*** "+nick+"@"+chan+" parts ("+string.join(word[3:],' ')[1:]+")"

        gname = string.join(string.split(chan,'_')[1:],'_')
        delPlayer(b,nick,gname)

        if b.channels.has_key(chan):
            if b.channels[chan]["nicks"].has_key(nick):
                del b.channels[chan]["nicks"][nick]
    elif (word[1] == "QUIT"): # user quits
        SUPRESS = True
        longHost = hostBreakup(word[0])
        nick, ident, domain = longHost
        print "*** "+nick+" quits ("+string.join(word[2:],' ')[1:]+")"

        delPlayer(b,nick)

        for chan in b.channels.iterkeys():
            if b.channels[chan]["nicks"].has_key(nick):
                del b.channels[chan]["nicks"][nick]
    elif (word[1] == "MODE"): # mode change
        SUPRESS = True
        longHost = hostBreakup(word[0])
        nick, ident, domain = longHost
        chan = word[2]
        print "*** "+nick+"@"+chan+" sets mode "+string.join(word[3:],' ')
        mode = 0
        param = 3
        for char in word[3]:
            if char == "+":
                mode = 1
            elif char == "-":
                mode = 2
            else:
                param += 1
                if b.channels.has_key(chan):
                    try:
                        nick = word[param]
                        if b.channels[chan]["nicks"].has_key(nick):
                            if mode == 1 and char not in b.channels[chan]["nicks"][nick]:
                                b.channels[chan]["nicks"][nick].append(char)
                            elif mode == 2 and char in b.channels[chan]["nicks"][nick]:
                                b.channels[chan]["nicks"][nick].remove(char)
                    except:
                        pass # this is a channel mode being set!
    elif (word[1] == "PRIVMSG"): # user messages a channel or erk directly
        SUPRESS = True
        longHost = hostBreakup(word[0])
        nick, ident, domain = longHost
        chan = word[2]
        replyto = nick if b.myNick == chan else chan
        text = string.join(word[3:],' ')[1:]
        print "<"+nick+"@"+chan+"> " + text # display to console

        words = string.split(text)
        if (text == "who are you?"):
            privMsg(b,replyto,b.myNick+".")
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
    replyto = nick if b.myNick == chan else chan
    if command == "checkmode":
        if params == "":
            params = "o"
        if b.channels.has_key(replyto):
            operators = []
            for checkNick in b.channels[replyto]["nicks"].iterkeys():
                if params in b.channels[replyto]["nicks"][checkNick]:
                    operators.append(checkNick)
            if len(operators):
                privMsg(b,replyto,"Mode match: "+string.join(operators))
            else:
                privMsg(b,replyto,"No mode matches in "+replyto)
        elif not replyto == chan:
            privMsg(b,replyto,"This command must be used in a channel.")
        else:
            privMsg(b,replyto,"No mode matches in "+replyto)
    elif command == "help":
        available = {}
        available["checkmode"] = "Debug. Lists nicks in current channel that match optional paramter mode. Default value is \"o\""
        available["channels"] = "Debug. Relays internal channel list, optional argument lists nicks associated with that channel."
        available["nicks"] = "Debug. Relays internal channel->nick list for current channel. Optional argument lists modes associated with given nick. Must be used in a channel."
        available["list"] = "Shows currently active games."
        available["create"] = "Creates a new game. Example: "+PREFIX+"create [name] [mode]"
        available["settings"] = "Debug. Shows IRC server settings, optional argument will list setting value."
        available["destroy"] = "Removes a currently active game. This can only be done by the game creator. Example: "+PREFIX+"destroy [channel]"
        if params == "":
            privMsg(b,replyto,"Commands: "+string.join(available))
        elif available.has_key(params):
            privMsg(b,replyto,available[params])
        else:
            privMsg(b,replyto,"Invalid help topic.")
    elif command == "channels":
        if params == "":
            if len(b.channels):
                privMsg(b,replyto,"Channels: "+string.join(b.channels))
            else:
                privMsg(b,replyto,"Channels: <none>")
        else:
            if b.channels.has_key(params):
                privMsg(b,replyto,"Channel "+params+": "+string.join(b.channels[params]["nicks"]))
            else:
                privMsg(b,replyto,"Invalid channel")
    elif command == "nicks":
        if replyto == chan:
            if params == "":
                if len(b.channels[chan]["nicks"]):
                    privMsg(b,replyto,"Nicks: "+string.join(b.channels[chan]["nicks"]))
                else:
                    privMsg(b,replyto,"Nicks: <none>")
            else:
                if b.channels[chan]["nicks"].has_key(params):
                    privMsg(b,replyto,"Nick "+params+": "+string.join(b.channels[chan]["nicks"][params]))
                else:
                    privMsg(b,replyto,"Invalid nick")
        else:
            privMsg(b,replyto,"Must be used in a channel.")
    elif command == "owners" and nick in b.owners:
        privMsg(b,replyto,"Owners: "+string.join(b.owners))
    elif command == "verify":
        if nick in b.owners:
            privMsg(b,replyto,"You are already verified.")
        elif params == b.ownerpassword:
            b.owners.append(nick)
            privMsg(b,replyto,"Password accepted. You are now verified.")
        else:
            privMsg(b,replyto,DENIED)
    elif command == "unverify" and nick in b.owners:
        b.owners.remove(nick)
        privMsg(b,replyto,"You have been unverified.")
    elif command == "mass" and nick in b.owners:
        if params == "voice":
            massMode(b,chan,"+","v",[b.myNick])
        elif params == "devoice":
            massMode(b,chan,"-","v",[b.myNick])
        elif params == "op":
            massMode(b,chan,"+","o",[b.myNick])
        elif params == "deop":
            massMode(b,chan,"-","o",[b.myNick])
        pass
    elif command == "list":
        if len(b.games) > 0:
            for gname in b.games.iterkeys():
                gowner = b.games[gname]["owner"]
                gchan = b.games[gname]["channel"]
                gstatus = b.games[gname]["status"]
                gmode = b.games[gname]["mode"]
                gstatus2 = ""
                if gstatus == 0:
                    gstatus2 = "creating"
                elif gstatus == 1:
                    gstatus2 = "waiting for players"
                else:
                    gstatus2 = "unknown ["+str(gstatus)+"]"
                privMsg(b,replyto,gchan+" ("+gmode+", "+gstatus2+") by "+gowner+" ["+str(playerCount(b,gname))+" players]")
        else:
            privMsg(b,replyto,"There are no games.")
    elif command == "restart" and nick in b.owners:
        privMsg(b,replyto,"Restarting....")
        b.send("QUIT :Restarting.\r\n")
        while len(b.sendqueue) > 0:
            pass
        time.sleep(1)        
        b.disconnect()
        print "Reconnecting...",
        b.connect()
    elif command == "die" and nick in b.owners:
        privMsg(b,replyto,"Shutting down....")
        b.send("QUIT :Shutting down.\r\n")
        while len(b.sendqueue) > 0:
            pass
        time.sleep(1)
        b.disconnect()
        sys.exit()
    elif command == "exec" and nick in b.owners:
        print "> "+params
        b.send(params+"\r\n")
    elif command == "start":
        try:
            if params != "":
                startchan = b.CHANNEL + "_" + string.split(params)[0]
            else:
                startchan = chan
            dostart = ""
            diequiet = False
            for gname in b.games.iterkeys():
                if b.games[gname]["channel"] == startchan:
                    if b.games[gname]["owner"] == nick or nick in b.owners:
                        dostart = gname
                    else:
                        privMsg(b,replyto,"You must be the game owner to start that game.")
                        diequiet = True
            if dostart == "":
                if not diequiet:                
                    privMsg(b,replyto,"Game does not exist. ("+startchan+")")                
            elif b.games[gname]["status"] < 1:
                privMsg(b,replyto,"Game cannot be started in its current state.")
            elif b.games[gname]["status"] > 1:
                privMsg(b,replyto,"Game has already been started.")
            else:
                gmode = b.games[gname]["mode"]
                need = modes[gmode]["min"] - len(b.games[gname]["players"])
                if need > 0:                    
                    privMsg(b,replyto,"Cannot start. Need at least "+str(need)+" more.")
                else:
                    startGame(b,gname) # looks good so far, try to start game.
        except:
            privMsg(b,replyto,"Oops! Unexpected exception in START command. Please check console for debug info.")
            print sys.exc_info()
    elif command == "create":
        gname = ""
        if params != "":
            sParams = string.split(params)
            gname = string.split(sParams[0],',')[0]
            try:
                gmode = sParams[1]
            except:
                gmode = "random"
        if gname == "":
            gname = "game"+str(len(b.games) + 1)
            gmode = "random"
        gchan = b.CHANNEL+"_"+gname
        if b.games.has_key(gname):
            privMsg(b,replyto,"That game ("+gname+") has already been created.")
        elif int(b.ircsettings['CHANNELLEN']) < len(gchan):
            privMsg(b,replyto,"Cannot create game, name too long.")
        elif gmode not in modes:
            privMsg(b,replyto,"Unknown game mode: "+gmode)
        else:
            b.games[gname] = {}
            b.games[gname]["owner"] = nick
            b.games[gname]["channel"] = gchan
            b.games[gname]["status"] = 0
            b.games[gname]["mode"] = gmode
            b.games[gname]["expire"] = time.time() + CREATE_EXPIRE
            b.games[gname]["reqop"] = False
            b.games[gname]["players"] = {}
            b.games[gname]["dead"] = []
            b.games[gname]["cycle"] = 0
            b.send("JOIN "+gchan+"\r\n")
    elif command == "modes":
        if params == "":
            privMsg(b,replyto,"Modes: "+string.join(modes))
        elif modes.has_key(params):
            privMsg(b,replyto,params+" mode: "+modes[params]["help"])
        else:
            privMsg(b,replyto,"Invalid mode.")
    elif command == "settings":
        try:
            if params == "":
                privMsg(b,replyto,"Settings: "+string.join(b.ircsettings))
            elif b.ircsettings.has_key(params):
                privMsg(b,replyto,params+" setting: "+str(b.ircsettings[params]))
            else:
                privMsg(b,replyto,"Invalid setting.")
        except:
            privMsg(b,replyto,"Oops, exception! "+sys.exc_info()[0])
    elif command == "join":
        joinGame(b,chan,nick,True)
    elif command == "forcestart" and nick in b.owners:
        if b.games.has_key(params):
            startGame(b,params)
        else:
            privMsg(b,replyto,"Game does not exist.")
    elif command == "destroy":
        try:
            if params != "":
                deschan = b.CHANNEL + "_" + string.split(params)[0]
            else:
                deschan = chan
            dodestroy = ""
            for gname in b.games.iterkeys():
                if b.games[gname]["channel"] == deschan:
                    if b.games[gname]["owner"] == nick or nick in b.owners:
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
    else:
        privMsg(b,replyto,"Unknown command: "+command)

def joinGame(b, chan, nick, manual = False):
    gname = string.join(string.split(chan,'_')[1:],'_')
    if b.games.has_key(gname):
        if nick != b.myNick and b.games[gname]["status"] == 1:
            if b.games[gname]["players"].has_key(nick) and manual:
                privMsg(b,chan,"You are already in this game, "+nick)
            else:
                b.games[gname]["players"][nick] = {}
                b.games[gname]["players"][nick]["specs"] = []
                b.games[gname]["players"][nick]["job"] = ""
                privMsg(b,chan,nick+" has joined the game. "+str(playerCount(b,gname))+" total")
        elif manual and b.games[gname]["status"] < 1:
            privMsg(b,chan,"Still attempting to create game. Cannot join.")
        elif manual and b.games[gname]["status"] > 1:
            privMsg(b,chan,"Game has already start, "+nick)
            
def startGame(b,gname):
    gchan = b.games[gname]["channel"]
    massMode(b,gchan,"-","o",[b.myNick]) # make sure nobody has ops
    massMode(b,gchan,"-","v",[b.myNick]) # make sure nobody has voice

    gowner = b.games[gname]["owner"]
    gmode = b.games[gname]["mode"]
    gtopic = gname+" ("+gmode+") "+str(playerCount(b,gname))+" players (assigning jobs)"
    
    b.send("MODE "+gchan+" +m\r\n") # moderate
    b.send("TOPIC "+gchan+" :"+gtopic+"\r\n") # set topic
    privMsg(b,gchan,"Game "+gname+" has started, sending job messages. Day 1 will happen once everyone has been notified.")

    gplayers = b.games[gname]["players"].copy()
    privMsg(b,gchan,"Players: "+string.join(gplayers))

# === assign jobs
    pool = gplayers.copy()

    # determine scum amount and select them
    minScum = int(round(float((float(modes[gmode]["scum_min"]) / 100) * len(gplayers))))
    maxScum = int(round(float((float(modes[gmode]["scum_max"]) / 100) * len(gplayers))))
    scumCount = int(random.randint(minScum,maxScum))
    scumPlayers = random.sample(pool,scumCount)

    # take the scum out of the pool, initialize them
    for p in scumPlayers:
        del pool[p]
        rj = rndJob(b,"mafia",False,gplayers)
        gplayers[p]["job"] = rj

    # assign scum specialties, if appropriate
    specScumPlayers = random.sample(scumPlayers,maxScum - minScum)
    for p in specScumPlayers:
        spec = rndSpec(b,"mafia",gplayers)
        if spec != "":
            gplayers[p]["specs"].append(spec)

    # determine special townie roles
    minRole = int(round(float((float(modes[gmode]["job_min"]) / 100) * len(gplayers))))
    maxRole = int(round(float((float(modes[gmode]["job_max"]) / 100) * len(gplayers))))
    roleCount = int(random.randint(minRole,maxRole))
    roleTownies = random.sample(pool,roleCount)

    # take the special roles out of the pool, initialize them
    for p in roleTownies:
        del pool[p]
        gplayers[p]["job"] = rndJob(b,"town",True,gplayers)

    # assign the rest of the pool
    for p in pool.iterkeys():
        gplayers[p]["job"] = rndJob(b,"town",False,gplayers)

    # commit the changes to the main dictionary
    b.games[gname]["players"] = gplayers

    privMsg(b,gchan,repr(b.games[gname]["players"]))
    
"""
modes["random"]["scum_min"] = 25.0
modes["random"]["scum_max"] = 34.0
modes["random"]["job_min"] = 10.0
modes["random"]["job_max"] = 16.0
"""
def rndJob(b,win,special,gplayers = {}):
    pool = []
    for job in jobs.iterkeys():
        count = 0
        for player in gplayers.iterkeys():
            if job in gplayers[player]["job"]:
                count += 1
        if win in jobs[job]["win"] and jobs[job]["special"] == special and count < jobs[job]["limit"]:
            pool.append(job)
    tmpreturn = "" if len(pool) < 1 else random.sample(pool,1)[0]
    return tmpreturn
def rndSpec(b,faction,gplayers = {}):
    pool = []
    for spec in specs.iterkeys():
        count = 0
        for player in gplayers.iterkeys():
            if spec in gplayers[player]["specs"]:
                count += 1
        if faction in specs[spec]["faction"] and count < specs[spec]["limit"]:
            pool.append(spec)
    return "" if len(pool) < 1 else random.sample(pool,1)[0]
def massMode(b,chan,switch,mode,butNot = []):
    if not b.channels.has_key(chan):
        return
    masslist = []
    for nick in b.channels[chan]["nicks"].iterkeys():
        if switch == "-":
            if nick not in butNot and b.hasMode(nick,mode,chan):
                masslist.append(nick)
        else:
            if nick not in butNot and not b.hasMode(nick,mode,chan):
                masslist.append(nick)
    i, queue = 0, []
    for nick in masslist:
        i += 1
        queue.append(nick)
        if i >= 5:
            modes, i, queue = mode * i, 0, []
            b.send("MODE "+chan+" "+switch+mode+" "+string.join(queue)+"\r\n")
            masslist.remove(nick)
    if len(queue) > 0:
        modes = mode * len(queue)
        b.send("MODE "+chan+" "+switch+(mode * len(queue))+" "+string.join(queue)+"\r\n")

def checkGameStatus(b):
    delgames = []
    if len(b.games) > 0:
        for gname in b.games.iterkeys():
            if b.games[gname]["status"] == 0:
                gchan = b.games[gname]["channel"]
                if b.hasMode(b.myNick,"o",b.games[gname]["channel"]):
                    b.games[gname]["status"] = 1
                    b.send("MODE "+gchan+" -m\r\n")
                    gowner = b.games[gname]["owner"]
                    gmode = b.games[gname]["mode"]
                    gtopic = gname+" ("+gmode+") waiting for players"
                    b.send("TOPIC "+gchan+" :"+gtopic+"\r\n")
                    privMsg(b,b.CHANNEL,"Game "+gname+" created. Join "+b.games[gname]["channel"]+" to play.")
                elif b.games[gname]["expire"] <= time.time():
                    privMsg(b,b.CHANNEL,"Could not create game "+gname)
                    b.send("PART "+gchan+"\r\n")
                    delgames.append(gname)
                elif b.games[gname]["expire"] - int(CREATE_EXPIRE / 2) <= time.time() and not b.games[gname]["reqop"]:
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
    print "<"+b.myNick+"@"+target+"> "+message
    b.send("PRIVMSG "+target+" :"+message+"\r\n")
    
def sendNotice(b,target,message):
    print "-"+b.myNick+"@"+target+"- "+message
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
