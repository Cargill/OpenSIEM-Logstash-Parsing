'''
To download SNMP trap receiver and pysnmp refer to https://bytesofgigabytes.com/snmp-protocol/python-snmp-trap-receiver/
'''

import logging
from logging.handlers import TimedRotatingFileHandler

from pysnmp.carrier.asyncore.dgram import udp
from pysnmp.entity import config, engine
from pysnmp.entity.rfc3413 import ntfrcv
from pysnmp.smi import builder
from pysnmp.hlapi import ObjectIdentity, ObjectType


from pysnmp.smi import builder, view, compiler


#############################################################################
# change logging level to INFO
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

#Formatting and timed file rotation
formatter = logging.Formatter('%(asctime)s MESSAGE %(message)s')
handler = TimedRotatingFileHandler('PATH\TO\SNMP\logs',
                                   when="m",
                                   interval=2, #every 2 mins
                                   backupCount=5) # 5 files

handler.setFormatter(formatter)
logger.addHandler(handler)


snmpEngine = engine.SnmpEngine()

TrapAgentAddress = '0.0.0.0'  # Trap listerner address ( 0.0.0.0 or IP of the host that collects snmp traps)
Port = 162  # trap listerner port 

print("Agent is listening SNMP Trap on " +
      TrapAgentAddress+" , Port : " + str(Port))
print(
    '--------------------------------------------------------------------------')
config.addTransport(
    snmpEngine,
    udp.domainName + (1,),
    udp.UdpTransport().openServerMode((TrapAgentAddress, Port))
)

# Configure community here
config.addV1System(snmpEngine, 'my-area', '<Comunity_string_goes_here>')

# Assemble MIB browser
mibBuilder = builder.MibBuilder()
mibViewController = view.MibViewController(mibBuilder)
compiler.addMibCompiler(mibBuilder)
# Pre-load MIB modules that define objects received in TRAPs
# Copy your MIB to python SNMP library: example - "C:\Program Files\Python3\Python3\Lib\site-packages\pysnmp\smi\mibs\MIB.py"
mibBuilder.loadModules('MIB')


def cbFun(snmpEngine, stateReference, contextEngineId, contextName,
          varBinds, cbCtx):
    obj_types = [ObjectType(ObjectIdentity(name), val).resolveWithMib(
        mibViewController).prettyPrint() for name, val in varBinds]
    trap_msg = ','.join(obj_types)
    logger.info(f'{trap_msg}')


ntfrcv.NotificationReceiver(snmpEngine, cbFun)

snmpEngine.transportDispatcher.jobStarted(1)

###################################################################################################################

try:
    snmpEngine.transportDispatcher.runDispatcher()
except:
    snmpEngine.transportDispatcher.closeDispatcher()
    raise
