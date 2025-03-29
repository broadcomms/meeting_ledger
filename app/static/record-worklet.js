// app/static/record-worklet.js
/*
class RecorderProcessor extends AudioWorkletProcessor {
    constructor() {
      super();
    }
  
    process(inputs, outputs, parameters) {
      const input = inputs[0];
      if (input && input[0]) {
        // Send the raw audio samples from channel 0 to the main thread.
        this.port.postMessage(input[0]);
      }
      // Keep processor alive.
      return true;
    }
  }
  
  registerProcessor('recorder-processor', RecorderProcessor);
  */

  // record-worklet.js

class RecorderProcessor extends AudioWorkletProcessor {
  process(inputs, outputs, parameters) {
    // Process the first input channel.
    const input = inputs[0][0];
    if (input && input.length > 0) {
      this.port.postMessage(input);
    }
    return true; // Keep processor alive.
  }
}

registerProcessor("recorder-processor", RecorderProcessor);