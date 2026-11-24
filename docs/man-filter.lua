local stringify = pandoc.utils.stringify

function Pandoc(document)
  local name = stringify(document.meta["man-name"] or document.meta.title)
  local description = stringify(document.meta.description or "Jihwija documentation")
  local blocks = document.blocks

  -- Markdown keeps its human-facing H1. The man page gets its title from
  -- metadata, so remove that duplicate heading before rendering.
  if #blocks > 0 and blocks[1].t == "Header" and blocks[1].level == 1 then
    table.remove(blocks, 1)
  end

  -- Promote the remaining Markdown headings into conventional man sections.
  for _, block in ipairs(blocks) do
    if block.t == "Header" then
      block.level = math.max(1, block.level - 1)
    end
  end

  local name_line = pandoc.Para({
    pandoc.Str(name),
    pandoc.Space(),
    pandoc.RawInline("man", "\\-"),
    pandoc.Space(),
    pandoc.Str(description),
  })
  table.insert(blocks, 1, name_line)
  table.insert(blocks, 1, pandoc.Header(1, "NAME"))

  document.blocks = blocks
  return document
end
