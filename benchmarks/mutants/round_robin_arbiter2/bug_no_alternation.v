module top_module (
    input clk,
    input reset,
    input [1:0] req,
    output reg [1:0] grant
);
    always @(posedge clk) begin
        if (reset) begin
            grant <= 2'b00;
        end else begin
            if (req == 2'b00) grant <= 2'b00;
            else if (req == 2'b01) grant <= 2'b01;
            else if (req == 2'b10) grant <= 2'b10;
            else grant <= 2'b01;
        end
    end
endmodule
