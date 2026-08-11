const { GoogleAuth } = require('google-auth-library');
const axios = require('axios');
const fs = require('fs');

async function main() {
  try {
    const auth = new GoogleAuth({
      keyFile: 'D:\\NongKanvelaAssistant\\rootanjai-app-firebase-adminsdk-fbsvc-a6bd296305.json',
      scopes: ['https://www.googleapis.com/auth/firebase', 'https://www.googleapis.com/auth/cloud-platform'],
    });

    const client = await auth.getClient();
    const token = await client.getAccessToken();

    const projectId = 'rootanjai-app';
    const headers = {
      Authorization: `Bearer ${token.token}`,
      'Content-Type': 'application/json',
    };

    console.log('Fetching Android Apps...');
    let res = await axios.get(`https://firebase.googleapis.com/v1beta1/projects/${projectId}/androidApps`, { headers });
    let androidApps = res.data.apps || [];
    
    if (androidApps.length === 0) {
      console.log('No Android App found. Creating one...');
      res = await axios.post(`https://firebase.googleapis.com/v1beta1/projects/${projectId}/androidApps`, {
        packageName: 'com.example.nongkanvelaassistant',
        displayName: 'NongKanvelaAssistant Android'
      }, { headers });
      console.log('Created Android App. Waiting 5s for config to be ready...');
      await new Promise(r => setTimeout(r, 5000));
      res = await axios.get(`https://firebase.googleapis.com/v1beta1/projects/${projectId}/androidApps`, { headers });
      androidApps = res.data.apps;
    }
    
    const androidAppId = androidApps[0].appId;
    console.log(`Getting config for Android App: ${androidAppId}`);
    res = await axios.get(`https://firebase.googleapis.com/v1beta1/projects/${projectId}/androidApps/${androidAppId}/config`, { headers });
    const configFileContents = Buffer.from(res.data.configFileContents, 'base64').toString('utf8');
    fs.writeFileSync('D:\\NongKanvelaAssistant\\app\\google-services.json', configFileContents);
    console.log('Saved google-services.json to Android project!');

    console.log('Fetching Web Apps...');
    res = await axios.get(`https://firebase.googleapis.com/v1beta1/projects/${projectId}/webApps`, { headers });
    let webApps = res.data.apps || [];

    if (webApps.length === 0) {
      console.log('No Web App found. Creating one...');
      res = await axios.post(`https://firebase.googleapis.com/v1beta1/projects/${projectId}/webApps`, {
        displayName: 'Dashboard Web'
      }, { headers });
      console.log('Created Web App. Waiting 5s for config to be ready...');
      await new Promise(r => setTimeout(r, 5000));
      res = await axios.get(`https://firebase.googleapis.com/v1beta1/projects/${projectId}/webApps`, { headers });
      webApps = res.data.apps;
    }

    const webAppId = webApps[0].appId;
    console.log(`Getting config for Web App: ${webAppId}`);
    res = await axios.get(`https://firebase.googleapis.com/v1beta1/projects/${projectId}/webApps/${webAppId}/config`, { headers });
    
    const webConfigStr = `export const firebaseConfig = ${JSON.stringify(res.data, null, 2)};`;
    fs.writeFileSync('D:\\NongKanvelaAssistant\\dashboard\\src\\firebase-config.js', webConfigStr);
    console.log('Saved firebase-config.js to Dashboard project!');

    console.log('SUCCESS!');
  } catch (err) {
    console.error('ERROR:', err.response ? err.response.data : err.message);
  }
}

main();
