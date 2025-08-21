const { default: makeWASocket, useMultiFileAuthState } = require('@whiskeysockets/baileys');

async function sendMessage(number, message) {
  const { state, saveCreds } = await useMultiFileAuthState('baileys_auth_info');
  const sock = makeWASocket({ auth: state });
  sock.ev.on('creds.update', saveCreds);
  await sock.waitForConnectionUpdate && sock.waitForConnectionUpdate();
  await sock.sendMessage(`${number}@s.whatsapp.net`, { text: message });
  sock.end();
}

const [,, number, ...msgParts] = process.argv;
if (!number || msgParts.length === 0) {
  console.log('Usage: node whatsapp.js <number> <message>');
  process.exit(1);
}

sendMessage(number, msgParts.join(' ')).catch(err => {
  console.error('Error sending message', err);
  process.exit(1);
});
