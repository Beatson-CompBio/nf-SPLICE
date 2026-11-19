process WRITE_INDEX {
    input:
    val matrices

    output:
    path "index.txt", emit: index

    exec:
    file("${task.workDir}/index.txt").text = matrices.collect { it.name }.join('\n')
}
