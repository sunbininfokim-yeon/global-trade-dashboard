'use strict';

// 공식 House/Senate roster XML을 로컬 캐시에 받는다. API 키는 쓰지 않는다.
// Senate는 자동 요청을 403으로 막을 수 있다. 그때는 브라우저로 XML을 저장한 뒤
// 이 스크립트를 다시 실행하면 변환만 한다.
const fs = require('node:fs');
const https = require('node:https');
const { URL } = require('node:url');
const {
  CACHE_DIR,
  HOUSE_SOURCE_URL,
  SENATE_SOURCE_URL,
  HOUSE_XML_PATH,
  SENATE_XML_PATH,
  SENATE_JSON_PATH,
  isHouseMemberDataXml,
  isSenateCvcXml,
  parseSenateCvcXml,
} = require('./lib/committee-membership-roster');

const USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36';
const MAX_REDIRECTS = 5;

function download(url, redirectsLeft = MAX_REDIRECTS) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    if (parsed.protocol !== 'https:') {
      reject(new Error(`HTTPS만 허용합니다: ${url}`));
      return;
    }
    const req = https.get(parsed, {
      headers: {
        'User-Agent': USER_AGENT,
        Accept: 'application/xml,text/xml,application/xhtml+xml,text/html;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
      },
    }, (res) => {
      const status = res.statusCode || 0;
      const location = res.headers.location;
      if (status >= 300 && status < 400 && location) {
        res.resume();
        if (redirectsLeft <= 0) {
          reject(new Error(`너무 많은 리다이렉트: ${url}`));
          return;
        }
        const next = new URL(location, parsed).toString();
        download(next, redirectsLeft - 1).then(resolve, reject);
        return;
      }
      const chunks = [];
      res.on('data', (chunk) => chunks.push(chunk));
      res.on('end', () => {
        const body = Buffer.concat(chunks).toString('utf8');
        resolve({ status, url: parsed.toString(), body });
      });
    });
    req.on('error', reject);
  });
}

function writeFile(filePath, contents) {
  fs.mkdirSync(CACHE_DIR, { recursive: true });
  fs.writeFileSync(filePath, contents);
}

async function fetchHouse() {
  const result = await download(HOUSE_SOURCE_URL);
  if (result.status !== 200 || !isHouseMemberDataXml(result.body)) {
    throw new Error(
      `House Clerk XML을 받지 못했습니다 (HTTP ${result.status}). 브라우저에서 ${HOUSE_SOURCE_URL} 을 열어 ${HOUSE_XML_PATH} 로 저장하세요.`,
    );
  }
  writeFile(HOUSE_XML_PATH, result.body);
  return HOUSE_XML_PATH;
}

function senateManualDownloadError(status) {
  return [
    `Senate CVC XML 자동 다운로드가 막혔습니다 (HTTP ${status}).`,
    `브라우저에서 ${SENATE_SOURCE_URL} 을 열어`,
    `${SENATE_XML_PATH} 로 저장한 뒤 이 스크립트를 다시 실행하세요.`,
    '저장한 XML에 <senators>와 <bioguideId>가 있어야 합니다. HTML Access Denied 페이지는 안 됩니다.',
  ].join(' ');
}

async function fetchSenateXml() {
  if (fs.existsSync(SENATE_XML_PATH) && isSenateCvcXml(fs.readFileSync(SENATE_XML_PATH, 'utf8'))) {
    console.log(`기존 Senate CVC XML을 사용합니다: ${SENATE_XML_PATH}`);
    return SENATE_XML_PATH;
  }
  const result = await download(SENATE_SOURCE_URL);
  if (result.status !== 200 || !isSenateCvcXml(result.body)) {
    throw new Error(senateManualDownloadError(result.status));
  }
  writeFile(SENATE_XML_PATH, result.body);
  return SENATE_XML_PATH;
}

function convertSenateXml() {
  const xml = fs.readFileSync(SENATE_XML_PATH, 'utf8');
  const parsed = parseSenateCvcXml(xml);
  writeFile(SENATE_JSON_PATH, `${JSON.stringify(parsed, null, 2)}\n`);
  return parsed;
}

async function main() {
  fs.mkdirSync(CACHE_DIR, { recursive: true });
  const housePath = await fetchHouse();
  console.log(`House Clerk XML 저장: ${housePath}`);
  try {
    const senatePath = await fetchSenateXml();
    const senate = convertSenateXml();
    console.log(`Senate CVC XML → JSON: ${senatePath} → ${SENATE_JSON_PATH}`);
    console.log(JSON.stringify({
      houseBytes: fs.statSync(housePath).size,
      senateXmlBytes: fs.statSync(senatePath).size,
      lastUpdate: senate.lastUpdate,
      senatorCount: senate.senatorCount,
      rows: senate.rows.length,
    }, null, 2));
  } catch (error) {
    if (fs.existsSync(SENATE_JSON_PATH)) {
      console.error(error.message);
      console.error(`기존 Senate JSON을 유지합니다: ${SENATE_JSON_PATH}`);
      return;
    }
    throw error;
  }
}

main().catch((error) => {
  console.error(error.message || error);
  process.exitCode = 1;
});
