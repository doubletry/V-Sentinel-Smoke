export function buildWhepPatchHeaders() {
  return {
    'Content-Type': 'application/trickle-ice-sdpfrag',
    'If-Match': '*',
  }
}

export function parseOfferData(sdp) {
  const offerData = { iceUfrag: '', icePwd: '', medias: [] }

  for (const line of String(sdp || '').split('\r\n')) {
    if (line.startsWith('m=')) {
      offerData.medias.push(line.slice(2))
    } else if (!offerData.iceUfrag && line.startsWith('a=ice-ufrag:')) {
      offerData.iceUfrag = line.slice('a=ice-ufrag:'.length)
    } else if (!offerData.icePwd && line.startsWith('a=ice-pwd:')) {
      offerData.icePwd = line.slice('a=ice-pwd:'.length)
    }
  }

  return offerData
}

export function generateSdpFragment(offerData, candidates) {
  if (!Array.isArray(candidates) || !candidates.length) {
    return `a=ice-ufrag:${offerData.iceUfrag}\r\na=ice-pwd:${offerData.icePwd}\r\n`
  }

  const candidatesByMedia = {}
  for (const candidate of candidates) {
    const mediaIndex = candidate.sdpMLineIndex
    if (!(mediaIndex in candidatesByMedia)) {
      candidatesByMedia[mediaIndex] = []
    }
    candidatesByMedia[mediaIndex].push(candidate)
  }

  let fragment = `a=ice-ufrag:${offerData.iceUfrag}\r\n`
  fragment += `a=ice-pwd:${offerData.icePwd}\r\n`

  for (let mediaIndex = 0; mediaIndex < offerData.medias.length; mediaIndex += 1) {
    if (!candidatesByMedia[mediaIndex]?.length) continue

    fragment += `m=${offerData.medias[mediaIndex]}\r\n`
    fragment += `a=mid:${mediaIndex}\r\n`
    for (const candidate of candidatesByMedia[mediaIndex]) {
      fragment += `a=${candidate.candidate}\r\n`
    }
  }

  return fragment
}
