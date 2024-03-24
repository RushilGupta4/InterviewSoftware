let socket;
let audioRecorder;
let videoRecorder;
let isResponding = false;
let wsUrl = 'ws://code.vondr.in/';
wsUrl = 'http://223.178.215.118:7000/';
// wsUrl = 'ws://localhost:8000/';

document.getElementById('respondingToggle').addEventListener('click', () => {
  isResponding = !isResponding;

  if (socket) {
    socket.emit('respondingStatus', isResponding);
  }
});

// Media Stream Setup
async function setupMediaStream() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: true,
      video: {
        frameRate: { ideal: 30, min: 24 },
      },
    });

    initializeAudioRecorder(stream);
    initializeVideoRecorder(stream);
    document.getElementById('videoPreview').srcObject = stream;
  } catch (error) {
    console.error('Error accessing media devices:', error);
  }
}

function initializeAudioRecorder(stream) {
  const audioTracks = stream.getAudioTracks();
  const audioStream = new MediaStream(audioTracks);

  audioRecorder = new RecordRTC(audioStream, {
    type: 'audio',
    // mimeType: 'audio/wav', // You can choose the audio format
    desiredSampRate: 16000,
    recorderType: StereoAudioRecorder,
    numberOfAudioChannels: 1,
    timeSlice: 500, // Send audio chunks every 500ms
    bufferSize: 16384,
    ondataavailable: async (blob) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        const arrayBuffer = reader.result;
        socket.emit('audioData', arrayBuffer);
      };
      reader.readAsArrayBuffer(blob);
    },
  });
}

function initializeVideoRecorder(stream) {
  const videoTracks = stream.getVideoTracks();
  const videoStream = new MediaStream(videoTracks);

  videoRecorder = new RecordRTC(videoStream, {
    type: 'video',
    mimeType: 'video/webm; codecs=H264',
    timeSlice: 500, // Send video chunks every 500ms
    ondataavailable: async (blob) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        const arrayBuffer = reader.result;
        socket.emit('videoData', arrayBuffer);
      };
      reader.readAsArrayBuffer(blob);
    },
  });
}

// Socket.IO and Event Handling
function startStreaming() {
  socket = io(wsUrl, {
    query: {
      interviewToken: '',
      email: '',
    },
  });

  socket.on('getRespondingStatus', (data) => {
    console.log(data);
    const isResponding = data.status;

    // Update the appearance of the toggle button
    if (isResponding) {
      document.getElementById('respondingToggle').classList.add('toggled');
      document.getElementById('respondingToggle').textContent = 'Stop Responding';
    } else {
      document.getElementById('respondingToggle').classList.remove('toggled');
      document.getElementById('respondingToggle').textContent = 'Start Responding';

      const message = data.message;

      if (message == 'Success') return;

      const responseContainer = document.getElementById('responseContainer');
      responseContainer.innerHTML += `<p>Message: ${message} <br>Timestamp: ${new Date().toISOString()}</p>`;
    }
  });

  socket.on('connect', () => {
    console.log('Connected to the server');

    document.getElementById('buttonStart').disabled = true;
    document.getElementById('buttonStop').disabled = false;
    document.getElementById('responseContainer').innerHTML = '<p>Streaming...</p>';

    // Show the start and stop responding buttons
    document.getElementById('respondingToggle').disabled = false;
  });

  socket.on('chat', (data) => {
    console.log(data);
    const responseContainer = document.getElementById('responseContainer');

    setTimeout(() => {
      responseContainer.innerHTML += `<p>Message: ${data.message} <br>Timestamp: ${data.timestamp}</p>`;
    }, 750);

    if (data.audio) {
      let audioSrc = 'data:audio/mp3;base64,' + data.audio;
      let audio = new Audio(audioSrc);
      audio
        .play()
        .then(() => console.log('Playing audio message...'))
        .catch((error) => console.error('Error playing the audio:', error));
    }

    if (data.interview_ended) {
      stopStreaming();
    }
  });

  audioRecorder.startRecording();
  videoRecorder.startRecording();
}

function stopStreaming() {
  audioRecorder.stopRecording();
  videoRecorder.stopRecording();

  // Hide the start and stop responding buttons
  socket.disconnect();
  document.getElementById('buttonStart').disabled = false;
  document.getElementById('buttonStop').disabled = true;
  document.getElementById('responseContainer').innerHTML += '<p>Stopped</p>';

  document.getElementById('respondingToggle').disabled = true;
  isResponding = false;
  document.getElementById('respondingToggle').classList.remove('toggled');
  document.getElementById('respondingToggle').textContent = 'Responding';
}

// Page Initialization
document.addEventListener('DOMContentLoaded', () => {
  setupMediaStream();

  document.getElementById('buttonStart').addEventListener('click', startStreaming);
  document.getElementById('buttonStop').addEventListener('click', stopStreaming);
});
