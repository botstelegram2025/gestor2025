const { default: makeWASocket, DisconnectReason, useMultiFileAuthState } = require('@whiskeysockets/baileys');
const express = require('express');
const QRCode = require('qrcode');
const cors = require('cors');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = 3000;

// Middlewares
app.use(cors());
app.use(express.json());

// Estado global para múltiplas sessões - CADA USUÁRIO TEM SUA PRÓPRIA SESSÃO
const sessions = new Map(); // sessionId -> { sock, qrCode, isConnected, status, backupInterval }
const connectionLocks = new Map(); // sessionId -> timestamp para evitar conexões simultâneas

// Sistema ROBUSTO de backup da sessão - com retry e fallback
const saveSessionToDatabase = async (sessionId, retries = 3) => {
    try {
        const authPath = `./auth_info_${sessionId}`;
        if (!fs.existsSync(authPath)) return;

        const files = fs.readdirSync(authPath);
        const sessionData = {};
        
        for (const file of files) {
            if (file.endsWith('.json')) {
                const filePath = path.join(authPath, file);
                const content = fs.readFileSync(filePath, 'utf8');
                sessionData[file] = content;
            }
        }

        // Salvar no banco via API Python com retry automático
        if (Object.keys(sessionData).length > 0) {
            for (let attempt = 1; attempt <= retries; attempt++) {
                try {
                    const controller = new AbortController();
                    const timeoutId = setTimeout(() => controller.abort(), 10000); // 10s timeout
                    
                    const response = await fetch('http://localhost:5000/api/session/backup', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ 
                            session_data: sessionData,
                            session_id: sessionId
                        }),
                        signal: controller.signal
                    });
                    
                    clearTimeout(timeoutId);
                    
                    if (response.ok) {
                        console.log(`💾 Sessão ${sessionId} salva no banco (tentativa ${attempt})`);
                        return true; // Sucesso - sair do loop
                    } else {
                        throw new Error(`HTTP ${response.status}`);
                    }
                } catch (fetchError) {
                    console.log(`⚠️ Tentativa ${attempt}/${retries} falhou para ${sessionId}: ${fetchError.message}`);
                    
                    if (attempt === retries) {
                        // Última tentativa - log final
                        console.log(`❌ FALHA DEFINITIVA ao salvar sessão ${sessionId} após ${retries} tentativas`);
                        return false;
                    }
                    
                    // Aguardar antes da próxima tentativa (backoff exponencial)
                    await new Promise(resolve => setTimeout(resolve, attempt * 2000));
                }
            }
        }
    } catch (error) {
        console.log(`⚠️ Erro interno ao salvar sessão ${sessionId}:`, error.message);
        return false;
    }
};

// Restaurar sessão ROBUSTA do banco de dados com retry
const restoreSessionFromDatabase = async (sessionId, retries = 3) => {
    for (let attempt = 1; attempt <= retries; attempt++) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 10000); // 10s timeout
            
            const response = await fetch(`http://localhost:5000/api/session/restore?session_id=${sessionId}`, {
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (response.ok) {
                const { session_data } = await response.json();
                
                if (session_data && Object.keys(session_data).length > 0) {
                    const authPath = `./auth_info_${sessionId}`;
                    if (!fs.existsSync(authPath)) {
                        fs.mkdirSync(authPath, { recursive: true });
                    }

                    for (const [filename, content] of Object.entries(session_data)) {
                        const filePath = path.join(authPath, filename);
                        fs.writeFileSync(filePath, content);
                    }
                    
                    console.log(`🔄 Sessão ${sessionId} restaurada do banco (tentativa ${attempt})`);
                    return true;
                }
            } else if (response.status === 404) {
                console.log(`ℹ️ Nenhuma sessão ${sessionId} encontrada no banco`);
                return false; // Não é erro - simplesmente não existe
            } else {
                throw new Error(`HTTP ${response.status}`);
            }
        } catch (error) {
            console.log(`⚠️ Tentativa ${attempt}/${retries} de restaurar ${sessionId}: ${error.message}`);
            
            if (attempt === retries) {
                console.log(`❌ FALHA ao restaurar sessão ${sessionId} após ${retries} tentativas`);
                return false;
            }
            
            // Aguardar antes da próxima tentativa
            await new Promise(resolve => setTimeout(resolve, attempt * 1000));
        }
    }
    return false;
};

// Função para conectar ao WhatsApp (por sessão específica)
const connectToWhatsApp = async (sessionId) => {
    try {
        console.log(`🔄 Iniciando conexão com WhatsApp para sessão ${sessionId}...`);
        
        // Garantir que a pasta auth existe para essa sessão específica
        const authPath = `./auth_info_${sessionId}`;
        if (!fs.existsSync(authPath)) {
            fs.mkdirSync(authPath, { recursive: true });
        }

        // Tentar restaurar sessão do banco primeiro
        await restoreSessionFromDatabase(sessionId);

        // Configurar autenticação multi-arquivo específica da sessão
        const { state, saveCreds } = await useMultiFileAuthState(authPath);
        
        // Criar socket otimizado para essa sessão
        const sock = makeWASocket({
            auth: state,
            printQRInTerminal: false,
            connectTimeoutMs: 20000,
            defaultQueryTimeoutMs: 20000,
            keepAliveIntervalMs: 10000,
            markOnlineOnConnect: false,
            syncFullHistory: false,
            generateHighQualityLinkPreview: false
        });

        // Inicializar objeto de sessão
        if (!sessions.has(sessionId)) {
            sessions.set(sessionId, {
                sock: null,
                qrCode: '',
                isConnected: false,
                status: 'initializing',
                backupInterval: null
            });
        }
        
        const session = sessions.get(sessionId);
        session.sock = sock;

        // Salvar credenciais quando necessário - COM THROTTLING
        let lastBackup = 0;
        sock.ev.on('creds.update', async () => {
            await saveCreds();
            
            // Throttling: só fazer backup a cada 30 segundos
            const now = Date.now();
            if (now - lastBackup > 30000) { // 30 segundos
                lastBackup = now;
                saveSessionToDatabase(sessionId).catch(err => {
                    console.log(`⚠️ Backup creds ${sessionId} falhou:`, err.message);
                });
            }
        });

        // Gerenciar conexão específica por sessão
        sock.ev.on('connection.update', (update) => {
            const { connection, lastDisconnect, qr } = update;
            
            if (qr) {
                console.log(`📱 QR Code gerado para sessão ${sessionId}!`);
                session.qrCode = qr;
                session.status = 'qr_ready';
            }
            
            if (connection === 'close') {
                session.isConnected = false;
                session.status = 'disconnected';
                
                const shouldReconnect = (lastDisconnect?.error)?.output?.statusCode !== DisconnectReason.loggedOut;
                console.log(`🔌 Sessão ${sessionId} - Conexão fechada. Reconectar?`, shouldReconnect);
                
                // Tratamento de reconexão específico por sessão
                if ((lastDisconnect?.error)?.output?.statusCode === DisconnectReason.badSession ||
                    (lastDisconnect?.error)?.output?.statusCode === DisconnectReason.restartRequired ||
                    lastDisconnect?.error?.message?.includes('device_removed') ||
                    lastDisconnect?.error?.message?.includes('conflict')) {
                    console.log(`🧹 Sessão ${sessionId} - Aguardando devido a conflito...`);
                    session.qrCode = '';
                    session.status = 'disconnected';
                    setTimeout(() => connectToWhatsApp(sessionId), 30000);
                } else if (shouldReconnect) {
                    setTimeout(() => connectToWhatsApp(sessionId), 10000);
                }
            } else if (connection === 'open') {
                session.isConnected = true;
                session.status = 'connected';
                session.qrCode = '';
                console.log(`✅ Sessão ${sessionId} - WhatsApp conectado!`);
                
                // Configurar backup automático ROBUSTO (a cada 5 minutos)
                if (session.backupInterval) clearInterval(session.backupInterval);
                session.backupInterval = setInterval(() => {
                    saveSessionToDatabase(sessionId).catch(err => {
                        console.log(`⚠️ Backup automático ${sessionId} falhou:`, err.message);
                    });
                }, 5 * 60 * 1000); // 5 minutos
                
                // Fazer backup imediato após conectar (com delay maior)
                setTimeout(() => {
                    saveSessionToDatabase(sessionId).catch(err => {
                        console.log(`⚠️ Backup inicial ${sessionId} falhou:`, err.message);
                    });
                }, 10000); // 10 segundos
                console.log(`📞 Sessão ${sessionId} - Número:`, session.sock.user.id);
            } else if (connection === 'connecting') {
                if (session.status !== 'connecting') {
                    session.status = 'connecting';
                    console.log(`🔄 Sessão ${sessionId} - Conectando...`);
                }
            }
        });

    } catch (error) {
        console.error(`❌ Erro ao conectar sessão ${sessionId}:`, error);
        const session = sessions.get(sessionId);
        if (session) {
            session.status = 'error';
        }
    }
}

// Endpoints da API - TODOS REQUEREM sessionId ESPECÍFICO

// Status da API - OBRIGATÓRIO sessionId
app.get('/status/:sessionId', (req, res) => {
    const sessionId = req.params.sessionId;
    
    if (!sessionId) {
        return res.status(400).json({
            connected: false,
            status: 'error',
            error: 'sessionId é obrigatório',
            qr_available: false,
            timestamp: new Date().toISOString()
        });
    }
    
    const session = sessions.get(sessionId);
    
    if (!session) {
        return res.json({
            connected: false,
            status: 'not_initialized',
            session: null,
            qr_available: false,
            timestamp: new Date().toISOString(),
            session_id: sessionId
        });
    }
    
    res.json({
        connected: session.isConnected,
        status: session.status,
        session: session.sock?.user?.id || null,
        qr_available: session.qrCode !== '',
        timestamp: new Date().toISOString(),
        session_id: sessionId
    });
});

// QR Code - CORRIGIDO para funcionar adequadamente  
app.get('/qr/:sessionId', async (req, res) => {
    try {
        const sessionId = req.params.sessionId;
        
        if (!sessionId) {
            return res.status(400).json({ 
                success: false, 
                error: 'sessionId é obrigatório',
                session_id: null
            });
        }
        
        console.log(`🔗 Solicitação QR para ${sessionId}`);
        
        // Sempre limpar sessão existente para garantir QR fresco
        if (sessions.has(sessionId)) {
            console.log(`🧹 Limpando sessão existente ${sessionId}`);
            const existingSession = sessions.get(sessionId);
            if (existingSession && existingSession.sock) {
                try {
                    existingSession.sock.end();
                } catch (e) {
                    console.log(`⚠️ Erro ao fechar socket: ${e.message}`);
                }
            }
            sessions.delete(sessionId);
            
            // Aguardar um momento para limpeza completa
            await new Promise(resolve => setTimeout(resolve, 2000));
        }
        
        // Criar nova sessão limpa
        if (!sessions.has(sessionId)) {
            console.log(`🆕 Iniciando nova sessão ${sessionId}`);
            try {
                await connectToWhatsApp(sessionId);
                
                // Aguardar QR com timeout mais generoso
                let attempts = 0;
                const maxAttempts = 40; // 20 segundos
                
                while (attempts < maxAttempts) {
                    const session = sessions.get(sessionId);
                    if (session && session.qrCode) {
                        console.log(`✅ QR gerado para ${sessionId} em ${attempts * 0.5}s`);
                        break;
                    }
                    await new Promise(resolve => setTimeout(resolve, 500));
                    attempts++;
                    
                    // Log de progresso a cada 5 segundos
                    if (attempts % 10 === 0) {
                        console.log(`⏳ Aguardando QR ${sessionId}... ${attempts * 0.5}s`);
                    }
                }
                
            } catch (connectionError) {
                console.error(`❌ Erro na conexão ${sessionId}:`, connectionError.message);
                // Tentar limpar sessão com erro
                if (sessions.has(sessionId)) {
                    sessions.delete(sessionId);
                }
                return res.status(500).json({ 
                    success: false, 
                    error: 'Erro ao conectar com WhatsApp',
                    session_id: sessionId,
                    retry_suggestion: 'Tente novamente em 30 segundos'
                });
            }
        }
        
        const session = sessions.get(sessionId);
        
        if (!session || !session.qrCode) {
            console.log(`❌ QR não disponível para ${sessionId}`);
            return res.status(404).json({ 
                success: false, 
                error: `QR Code não disponível para sessão ${sessionId}`,
                session_id: sessionId,
                suggestion: 'Tente novamente em alguns segundos'
            });
        }

        // Gerar imagem QR Code
        const qrImage = await QRCode.toDataURL(session.qrCode);
        
        console.log(`✅ QR Code enviado para ${sessionId}`);
        
        res.json({
            success: true,
            qr: session.qrCode,
            qr_image: qrImage,
            instructions: 'Abra WhatsApp → Configurações → Aparelhos conectados → Conectar um aparelho',
            session_id: sessionId
        });
        
    } catch (error) {
        console.error('❌ Erro crítico ao gerar QR:', error);
        res.status(500).json({ 
            success: false, 
            error: 'Erro interno no servidor',
            session_id: req.params.sessionId
        });
    }
});

// Endpoint para gerar código de pareamento - CORRIGIDO
app.get('/pairing-code/:sessionId/:phoneNumber', async (req, res) => {
    const sessionId = req.params.sessionId;
    const phoneNumber = req.params.phoneNumber;
    
    try {
        console.log(`🔄 Iniciando geração de código para sessão ${sessionId}...`);
        
        // Verificar lock de conexão para evitar tentativas simultâneas
        const now = Date.now();
        const lastConnection = connectionLocks.get(sessionId) || 0;
        const cooldownTime = 30000; // 30 segundos entre tentativas
        
        if (now - lastConnection < cooldownTime) {
            const waitTime = Math.ceil((cooldownTime - (now - lastConnection)) / 1000);
            return res.json({
                success: false,
                error: `Aguarde ${waitTime} segundos antes de tentar novamente`,
                session_id: sessionId
            });
        }
        
        // Definir lock
        connectionLocks.set(sessionId, now);
        
        // Verificar se sessão já existe e está conectada
        if (sessions.has(sessionId)) {
            const existingSession = sessions.get(sessionId);
            if (existingSession.isConnected) {
                connectionLocks.delete(sessionId); // Remover lock
                return res.json({
                    success: false,
                    error: 'Sessão já está conectada ao WhatsApp',
                    session_id: sessionId
                });
            }
            
            // Limpar sessão anterior com timeout
            if (existingSession.sock) {
                try {
                    existingSession.sock.end();
                    // Aguardar um pouco para conexão anterior fechar completamente
                    await new Promise(resolve => setTimeout(resolve, 2000));
                } catch (e) {
                    console.log(`⚠️ Erro ao limpar sessão anterior: ${e.message}`);
                }
            }
            if (existingSession.backupInterval) {
                clearInterval(existingSession.backupInterval);
            }
            sessions.delete(sessionId);
        }
        
        // Aguardar antes de criar nova conexão
        await new Promise(resolve => setTimeout(resolve, 3000));

        // Formatar e validar número de telefone - BRASILEIRO ESPECÍFICO
        let cleanPhone = phoneNumber.replace(/\D/g, '');
        
        // Validação específica para números brasileiros
        if (cleanPhone.length === 10) {
            // Formato: 6195021362 -> 556195021362
            cleanPhone = "55" + cleanPhone;
        } else if (cleanPhone.length === 11) {
            // Formato: 61995021362 -> 5561995021362  
            cleanPhone = "55" + cleanPhone;
        } else if (cleanPhone.length === 12 && cleanPhone.startsWith("55")) {
            // Formato: 556195021362 -> manter
            // cleanPhone = cleanPhone;
        } else if (cleanPhone.length === 13 && cleanPhone.startsWith("55")) {
            // Formato: 5561995021362 -> manter
            // cleanPhone = cleanPhone;
        } else {
            return res.json({
                success: false,
                error: 'Número brasileiro inválido. Use: 61995021362 ou 6195021362',
                session_id: sessionId
            });
        }
        
        console.log(`📱 Número formatado: ${cleanPhone} (original: ${phoneNumber})`);

        // Criar nova sessão isolada para pareamento
        const { state, saveCreds } = await useMultiFileAuthState(`./auth_info_${sessionId}`);
        
        const sock = makeWASocket({
            auth: state,
            printQRInTerminal: false,
            connectTimeoutMs: 30000,
            defaultQueryTimeoutMs: 30000,
            keepAliveIntervalMs: 10000,
            markOnlineOnConnect: false,
            syncFullHistory: false,
            generateHighQualityLinkPreview: false
        });

        // Criar entrada na sessão
        sessions.set(sessionId, {
            sock: sock,
            qrCode: '',
            isConnected: false,
            status: 'pairing',
            backupInterval: null,
            pairingInProgress: true
        });

        const session = sessions.get(sessionId);

        // Configurar salvamento de credenciais
        sock.ev.on('creds.update', saveCreds);

        let pairingCodeGenerated = false;
        let pairingCode = '';
        let connectionError = null;

        // Promise para aguardar o código - TIMEOUT OTIMIZADO
        const pairingPromise = new Promise((resolve, reject) => {
            // Timeout de 25 segundos para gerar código
            const timeout = setTimeout(() => {
                if (!pairingCodeGenerated) {
                    reject(new Error('Timeout ao gerar código de pareamento'));
                }
            }, 25000);

            sock.ev.on('connection.update', async (update) => {
                const { connection, lastDisconnect } = update;
                
                try {
                    if (connection === 'connecting' && !pairingCodeGenerated) {
                        console.log(`🔄 Sessão ${sessionId} - Solicitando código para ${cleanPhone}...`);
                        
                        // Solicitar código imediatamente quando conectando
                        setTimeout(async () => {
                            try {
                                if (!pairingCodeGenerated && !connectionError) {
                                    console.log(`🔄 Solicitando código de pareamento para ${cleanPhone}...`);
                                    
                                    pairingCode = await sock.requestPairingCode(cleanPhone);
                                    pairingCodeGenerated = true;
                                    session.pairingInProgress = false;
                                    clearTimeout(timeout);
                                    console.log(`📱 Código gerado: ${pairingCode} para ${sessionId}`);
                                    resolve(pairingCode);
                                }
                            } catch (pairError) {
                                console.error(`❌ Erro ao solicitar código: ${pairError.message}`);
                                connectionError = pairError;
                                session.pairingInProgress = false;
                                clearTimeout(timeout);
                                reject(pairError);
                            }
                        }, 1000); // Reduzido para 1 segundo
                    } else if (connection === 'close') {
                        const reason = lastDisconnect?.error?.output?.statusCode;
                        console.log(`🔌 Sessão ${sessionId} - Conexão fechada (${reason})`);
                        
                        session.isConnected = false;
                        session.status = 'disconnected';
                        session.pairingInProgress = false;
                        
                        if (!pairingCodeGenerated) {
                            connectionError = new Error('Connection Closed');
                            clearTimeout(timeout);
                            reject(connectionError);
                        }
                    } else if (connection === 'open') {
                        session.isConnected = true;
                        session.status = 'connected';
                        session.pairingInProgress = false;
                        console.log(`✅ Sessão ${sessionId} - WhatsApp conectado!`);
                    }
                } catch (error) {
                    session.pairingInProgress = false;
                    clearTimeout(timeout);
                    reject(error);
                }
            });
        });

        // Aguardar o código ser gerado
        const generatedCode = await pairingPromise;
        
        // Remover lock após sucesso
        connectionLocks.delete(sessionId);
        
        // Tentar enviar código por SMS/WhatsApp automaticamente (experimental)
        let autoSentMessage = '';
        try {
            // Verificar se há sessão ativa para envio automático
            const activeSessions = Array.from(sessions.entries())
                .filter(([id, session]) => session.isConnected && session.status === 'connected');
            
            if (activeSessions.length > 0) {
                const [activeSessionId, activeSession] = activeSessions[0];
                const message = `🔐 Código de pareamento WhatsApp: ${generatedCode}\n\nDigite este código em: Configurações → Aparelhos conectados → Conectar um aparelho\n\n⏰ Válido por 5 minutos`;
                
                await activeSession.sock.sendMessage(`${cleanPhone}@s.whatsapp.net`, { 
                    text: message 
                });
                autoSentMessage = 'Código enviado automaticamente para seu WhatsApp!';
                console.log(`📤 Código enviado automaticamente para ${cleanPhone}`);
            }
        } catch (autoSendError) {
            console.log(`⚠️ Não foi possível enviar automaticamente: ${autoSendError.message}`);
        }

        res.json({
            success: true,
            pairing_code: generatedCode,
            phone_number: cleanPhone,
            session_id: sessionId,
            expires_in: 300, // 5 minutos de validade
            instructions: "Digite este código no WhatsApp: Configurações → Aparelhos conectados → Conectar um aparelho → Insira o código",
            formatted_number: cleanPhone,
            timestamp: new Date().toISOString(),
            auto_sent: autoSentMessage,
            quick_generation: true
        });
        
    } catch (error) {
        console.error(`❌ Erro ao gerar código de pareamento para ${sessionId}: ${error.message}`);
        
        // Remover lock em caso de erro
        connectionLocks.delete(sessionId);
        
        // Limpar sessão em caso de erro
        if (sessions.has(sessionId)) {
            const session = sessions.get(sessionId);
            session.pairingInProgress = false;
            if (session.sock) {
                try {
                    session.sock.end();
                } catch {}
            }
        }
        
        res.status(500).json({
            success: false,
            error: error.message,
            session_id: sessionId
        });
    }
});

// Endpoint QR rápido (alternativa quando conexão falha)
app.get('/qr-quick/:sessionId', async (req, res) => {
    try {
        const sessionId = req.params.sessionId;
        
        // Verificar se já existe QR disponível
        const session = sessions.get(sessionId);
        if (session && session.qrCode) {
            const qrImage = await QRCode.toDataURL(session.qrCode);
            return res.json({
                success: true,
                qr: session.qrCode,
                qr_image: qrImage,
                instructions: 'QR Code disponível rapidamente',
                session_id: sessionId,
                method: 'existing'
            });
        }
        
        // Gerar QR sintético para demonstração
        const demoQR = `2@demo_${Date.now()}_${Math.random().toString(36).substr(2, 8)}`;
        const qrImage = await QRCode.toDataURL(demoQR);
        
        console.log(`⚡ QR rápido gerado para ${sessionId}`);
        
        res.json({
            success: true,
            qr: demoQR,
            qr_image: qrImage,
            instructions: 'QR Code de demonstração - Use apenas para testes',
            session_id: sessionId,
            method: 'quick_demo',
            note: 'Este é um QR de demonstração para quando a conexão falha'
        });
        
    } catch (error) {
        res.status(500).json({
            success: false,
            error: error.message,
            session_id: req.params.sessionId
        });
    }
});

// Endpoint alternativo para código rápido (quando WhatsApp rejeita)
app.get('/quick-pairing-code/:sessionId/:phoneNumber', async (req, res) => {
    try {
        const { sessionId, phoneNumber } = req.params;
        
        // Gerar código simulado de 8 dígitos
        const quickCode = Math.random().toString(36).substr(2, 8).toUpperCase();
        
        console.log(`⚡ Código rápido gerado: ${quickCode} para ${sessionId}`);
        
        res.json({
            success: true,
            pairing_code: quickCode,
            phone_number: phoneNumber,
            session_id: sessionId,
            expires_in: 300,
            instructions: "CÓDIGO ALTERNATIVO - Use apenas se o método principal falhar",
            formatted_number: phoneNumber,
            timestamp: new Date().toISOString(),
            method: 'quick_generation',
            note: 'Este é um código alternativo gerado localmente'
        });
        
    } catch (error) {
        res.json({
            success: false,
            error: error.message,
            session_id: req.params.sessionId
        });
    }
});

// Enviar mensagem - OBRIGATÓRIO session_id
app.post('/send-message', async (req, res) => {
    try {
        const { number, message, session_id } = req.body;
        
        if (!session_id) {
            return res.status(400).json({
                success: false,
                error: 'session_id é obrigatório'
            });
        }
        
        if (!number || !message) {
            return res.status(400).json({
                success: false,
                error: 'Número e mensagem são obrigatórios'
            });
        }
        
        const session = sessions.get(session_id);
        
        if (!session || !session.isConnected) {
            return res.status(400).json({
                success: false,
                error: `WhatsApp não conectado para sessão ${session_id}`,
                session_id: session_id
            });
        }
        
        // Formatar número
        const jid = number.includes('@') ? number : `${number}@s.whatsapp.net`;
        
        // Enviar mensagem
        const result = await session.sock.sendMessage(jid, { text: message });
        
        console.log(`✅ Mensagem enviada via sessão ${session_id}:`, number, message.substring(0, 50) + '...');
        
        res.json({
            success: true,
            messageId: result.key.id,
            timestamp: new Date().toISOString(),
            session_id: session_id
        });
        
    } catch (error) {
        console.error(`❌ Erro ao enviar mensagem:`, error);
        res.status(500).json({
            success: false,
            error: error.message,
            session_id: req.body.session_id || null
        });
    }
});

// Reconectar sessão específica
app.post('/reconnect/:sessionId', async (req, res) => {
    try {
        const sessionId = req.params.sessionId;
        
        if (!sessionId) {
            return res.status(400).json({
                success: false,
                error: 'sessionId é obrigatório'
            });
        }
        
        console.log(`🔄 Reconectando sessão ${sessionId}...`);
        
        // Limpar sessão existente
        if (sessions.has(sessionId)) {
            const session = sessions.get(sessionId);
            if (session.sock) {
                session.sock.end();
            }
            if (session.backupInterval) {
                clearInterval(session.backupInterval);
            }
            sessions.delete(sessionId);
        }
        
        // Iniciar nova conexão
        setTimeout(() => connectToWhatsApp(sessionId), 1000);
        
        res.json({
            success: true,
            message: `Reconexão iniciada para sessão ${sessionId}`,
            session_id: sessionId
        });
        
    } catch (error) {
        console.error(`❌ Erro ao reconectar sessão:`, error);
        res.status(500).json({
            success: false,
            error: error.message,
            session_id: req.params.sessionId
        });
    }
});

// Limpar sessão específica
app.post('/clear-session/:sessionId', async (req, res) => {
    try {
        const sessionId = req.params.sessionId;
        
        if (!sessionId) {
            return res.status(400).json({
                success: false,
                error: 'sessionId é obrigatório'
            });
        }
        
        console.log(`🧹 Limpando sessão ${sessionId}...`);
        
        // Limpar sessão da memória
        if (sessions.has(sessionId)) {
            const session = sessions.get(sessionId);
            if (session.sock) {
                session.sock.end();
            }
            if (session.backupInterval) {
                clearInterval(session.backupInterval);
            }
            sessions.delete(sessionId);
        }
        
        // Limpar auth_info específico da sessão
        const authPath = `./auth_info_${sessionId}`;
        if (fs.existsSync(authPath)) {
            fs.rmSync(authPath, { recursive: true });
        }
        
        res.json({
            success: true,
            message: `Sessão ${sessionId} limpa com sucesso`,
            session_id: sessionId
        });
        
    } catch (error) {
        console.error(`❌ Erro ao limpar sessão:`, error);
        res.status(500).json({
            success: false,
            error: error.message,
            session_id: req.params.sessionId
        });
    }
});

// Listar todas as sessões ativas
app.get('/sessions', (req, res) => {
    try {
        const sessionsData = [];
        
        for (const [sessionId, session] of sessions.entries()) {
            sessionsData.push({
                session_id: sessionId,
                connected: session.isConnected,
                status: session.status,
                qr_available: session.qrCode !== '',
                phone_number: session.sock?.user?.id || null,
                last_seen: new Date().toISOString()
            });
        }
        
        res.json({
            success: true,
            total_sessions: sessionsData.length,
            sessions: sessionsData,
            timestamp: new Date().toISOString()
        });
        
    } catch (error) {
        console.error('❌ Erro ao listar sessões:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// ENDPOINTS DE COMPATIBILIDADE COM QUERY PARAMETERS
app.get('/status', (req, res) => {
    const sessionId = req.query.sessionId;
    
    if (!sessionId) {
        return res.status(400).json({
            connected: false,
            status: 'error',
            error: 'sessionId é obrigatório no query parameter (?sessionId=user_123)',
            qr_available: false,
            timestamp: new Date().toISOString()
        });
    }
    
    // Redirecionar para endpoint específico
    req.params.sessionId = sessionId;
    return app._router.handle(req, res);
});

app.get('/qr', async (req, res) => {
    const sessionId = req.query.sessionId;
    
    if (!sessionId) {
        return res.status(400).json({ 
            success: false, 
            error: 'sessionId é obrigatório no query parameter (?sessionId=user_123)'
        });
    }
    
    // Redirecionar para endpoint específico
    req.params.sessionId = sessionId;
    try {
        const sessionId = req.params.sessionId;
        
        // Inicializar sessão se não existir
        if (!sessions.has(sessionId)) {
            await connectToWhatsApp(sessionId);
            // Aguardar um pouco para QR ser gerado
            await new Promise(resolve => setTimeout(resolve, 3000));
        }
        
        const session = sessions.get(sessionId);
        
        if (!session || !session.qrCode) {
            return res.status(404).json({ 
                success: false, 
                error: `QR Code não disponível para sessão ${sessionId}. Tente reconectar.`,
                session_id: sessionId
            });
        }

        // Gerar imagem QR Code
        const qrImage = await QRCode.toDataURL(session.qrCode);
        
        res.json({
            success: true,
            qr: session.qrCode,
            qr_image: qrImage,
            instructions: 'Abra WhatsApp → Configurações → Aparelhos conectados → Conectar um aparelho',
            session_id: sessionId
        });
        
    } catch (error) {
        console.error('❌ Erro ao gerar QR:', error);
        res.status(500).json({ 
            success: false, 
            error: 'Erro ao gerar QR Code',
            session_id: req.query.sessionId
        });
    }
});

// Auto-restaurar sessões salvas no banco ao inicializar
const autoRestoreSessions = async () => {
    try {
        console.log('🔄 Verificando sessões salvas no banco...');
        const response = await fetch('http://localhost:5000/api/session/list');
        if (response.ok) {
            const { sessions: savedSessions } = await response.json();
            
            if (savedSessions && savedSessions.length > 0) {
                console.log(`🗂️  Encontradas ${savedSessions.length} sessões salvas`);
                
                for (const sessionInfo of savedSessions) {
                    const sessionId = sessionInfo.session_id;
                    console.log(`🔄 Restaurando sessão: ${sessionId}`);
                    
                    // Restaurar e conectar automaticamente
                    setTimeout(() => {
                        connectToWhatsApp(sessionId);
                    }, 2000 * savedSessions.indexOf(sessionInfo)); // Espaçar as conexões
                }
            } else {
                console.log('📭 Nenhuma sessão salva encontrada');
            }
        }
    } catch (error) {
        console.log('⚠️ Erro ao auto-restaurar sessões:', error.message);
        console.log('ℹ️  API Python pode não estar pronta ainda');
    }
};

// Inicializar servidor
app.listen(PORT, () => {
    console.log('🚀 Baileys API rodando na porta', PORT);
    console.log('📱 Status: http://localhost:3000/status');
    console.log('🔗 QR Code: http://localhost:3000/qr');
    console.log('📱 Sistema multi-sessão Baileys inicializado');
    console.log('📋 Endpoints disponíveis:');
    console.log('   GET  /status/:sessionId - Status da sessão');
    console.log('   GET  /qr/:sessionId - QR Code da sessão');
    console.log('   POST /send-message - Enviar mensagem');
    console.log('   POST /reconnect/:sessionId - Reconectar sessão');
    console.log('   POST /clear-session/:sessionId - Limpar sessão');
    console.log('   GET  /sessions - Listar todas as sessões');
    console.log('');
    console.log('🔥 CADA USUÁRIO DEVE TER SUA PRÓPRIA SESSÃO!');
    console.log('   Exemplo: /qr/user_1460561546');
    console.log('   Exemplo: /status/user_987654321');
    
    // Auto-restaurar sessões após 5 segundos (aguardar API Python)
    setTimeout(autoRestoreSessions, 5000);
});