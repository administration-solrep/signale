application.register('table-anchor', class extends Stimulus.Controller {
    initialize() {
        if (location.hash) {
            /* Waiting for the next tick to supplement previous browser behavior. */
            setTimeout(() => {
                const element = document.querySelector(window.location.hash)
                const target = element.getBoundingClientRect()
                window.scrollTo({
                    /* Position the highlighted element in the middle of the page. */
                    top: window.scrollY + target.top - window.innerHeight / 2 + target.height / 2,
                    behavior: 'smooth'
                })
            }, 1)
        }
    }
})

/**
    Filtre spécifique pour les tags car ils sont
    affichés dans une liste SelectizeJS et le filtre
    StimulusJS n'est pas compatible avec cette librairie
**/
function filterTags(target){
    amendements = $("table.table tr[data-tag]")
    initialCount = parseInt($("div.content").attr("data-amendements-filters-initial-count"))
    count = 0

    for(i=0; i < amendements.length; i++){
        if(!target.length){
            amendements[i].classList.remove("hidden-tag")
        } else {
            nbMatches = findMatches(target, amendements[i])
            count = nbDisplay(nbMatches, target, amendements[i])
        }
    }
    updateCount(target, initialCount, count)
}

function findMatches(target, amendement){
    nbMatches = 0
    tags = amendement.attributes["data-tag"].value
    tags_splitted = tags.split("|")
    for(x=0; x < target.length; x++){
        if(tags_splitted.includes(target[x].toLowerCase())){
            nbMatches += 1
        }
    }
    return nbMatches
}

function nbDisplay(nbMatches, target, amendement){
    if(nbMatches == target.length){
        count += amendement.getAttribute("data-amendement").split(",").length
        amendement.classList.remove("hidden-tag")
    } else {
        amendement.classList.add("hidden-tag")
    }
    return count
}

function updateCount(target, initial, count){
    if(!target.length){
        const plural = initial > 1 ? 's' : ''
        nbLib = initial + " amendement" + plural
    } else {
        const plural = count > 1 ? 's' : ''
        nbLib = count + " amendement" + plural + " sur " + initial
    }
    $(".content .options span").html(nbLib)
}

function getURLParam(name) {
    const urlParams = new URLSearchParams(window.location.search)
    return urlParams.get(name) || ''
}

function setURLParam(name, value) {
    if (history.replaceState) {
        const newURL = new URL(window.location.href)
        if (value !== '') {
            newURL.searchParams.set(name, value)
        } else {
            newURL.searchParams.delete(name)
        }
        window.history.replaceState({ path: newURL.href }, '', newURL.href)
    }
}

function addInDataTagAttribute(amdt_num, option){
    selected = $('tr[data-amendement="' + amdt_num +'"]').attr('data-tag')
    if(selected === ""){
        newDataTags = option.toLowerCase()
    } else {
        newDataTags = selected + "|" + option.toLowerCase()
    }
    $('tr[data-amendement="' + amdt_num +'"]').attr('data-tag', newDataTags)
}

function removeInDataTagAttribute(amdt_num, option){
    selected = $('tr[data-amendement="' + amdt_num +'"]').attr('data-tag')
    if(selected !== ""){
        tags = selected.split('|')
        newDataTags = []
        for(i=0; i<tags.length; i++){
            if(option.toLowerCase() != tags[i]){
                newDataTags.push(tags[i])
            }
        }
        $('tr[data-amendement="' + amdt_num +'"]').attr('data-tag', newDataTags.join("|"))
    }
}
